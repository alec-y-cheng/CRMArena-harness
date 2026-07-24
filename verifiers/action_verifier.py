from difflib import get_close_matches
import re
from typing import Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from verifiers.schema_utils import SchemaIndex, build_schema_index, normalize_query
from verifiers.soql_parser_client import SOQLParseResult, parse_soql
from verifiers.types import VerificationResult


READ_ONLY_START_RE = re.compile(r"^\s*(select|find)\b", re.IGNORECASE)
WRITE_OR_ADMIN_RE = re.compile(
    r"\b(insert|update|upsert|delete|undelete|merge|create|alter|drop|truncate|"
    r"grant|revoke|commit|rollback|set|reset|deploy|apex)\b",
    re.IGNORECASE,
)
IDENT_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*(?:__[a-zA-Z])?\b")
SOQL_KEYWORDS = {
    "ALL",
    "AND",
    "ASC",
    "BY",
    "CALENDAR_MONTH",
    "CALENDAR_QUARTER",
    "CALENDAR_YEAR",
    "COUNT",
    "COUNT_DISTINCT",
    "DAY_ONLY",
    "DESC",
    "FALSE",
    "FIRST",
    "FROM",
    "GROUP",
    "HAVING",
    "IN",
    "INCLUDES",
    "LAST",
    "LIKE",
    "LIMIT",
    "NOT",
    "NULL",
    "OFFSET",
    "OR",
    "ORDER",
    "SELECT",
    "TRUE",
    "WHERE",
    "AVG",
    "MAX",
    "MIN",
    "SUM",
}
DATE_COMPARISON_RE = re.compile(
    r"\b([A-Za-z_][A-Za-z0-9_.]*(?:Date|DateTime|Time|From|To))\b\s*(=|!=|<=|>=|<|>)\s*('?\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{4})?)?'?)",
    re.IGNORECASE,
)
SQL_FUNCTION_RE = re.compile(
    r"\b(DATEDIFF|DATE_DIFF|TIMESTAMPDIFF|DATEADD|STRFTIME|EXTRACT|YEAR|MONTH)\s*\(",
    re.IGNORECASE,
)
UNSUPPORTED_DATE_FUNCTION_RE = re.compile(r"\bDATEVALUE\s*\(", re.IGNORECASE)
EMPTY_COUNT_RE = re.compile(r"\bCOUNT\s*\(\s*\)", re.IGNORECASE)
SQL_CONDITIONAL_AGG_RE = re.compile(r"\b(CASE\s+WHEN|COUNTIF)\b", re.IGNORECASE)
ARITHMETIC_EXPRESSION_RE = re.compile(
    r"\)\s*(?:\*|/|\+|-)\s*\d|\b[A-Za-z_][A-Za-z0-9_.]*\s*(?:\*|/|\+|-)\s*\b[A-Za-z_][A-Za-z0-9_.]*",
    re.IGNORECASE,
)
SQL_ONLY_CONSTRUCT_RE = re.compile(r"\b(JOIN|UNION)\b", re.IGNORECASE)
SCALAR_SUBQUERY_RE = re.compile(r"(=|!=|<=|>=|<|>)\s*\(\s*SELECT\b", re.IGNORECASE)
AS_ALIAS_RE = re.compile(r"\bAS\s+[A-Za-z_][A-Za-z0-9_]*\b", re.IGNORECASE)
ORDER_BY_AGGREGATE_ARITHMETIC_RE = re.compile(
    r"\bORDER\s+BY\b[^\\n]*(?:COUNT|SUM|AVG|MIN|MAX)\s*\([^)]*\)\s*(?:/|\*|\+|-)",
    re.IGNORECASE,
)
SQL_DATE_LITERAL_RE = re.compile(r"\bDATE\s+['\"]\d{4}-\d{2}-\d{2}['\"]", re.IGNORECASE)
SELECT_DISTINCT_RE = re.compile(r"^\s*SELECT\s+DISTINCT\b", re.IGNORECASE)
ID_LITERAL_COMPARISON_RE = re.compile(
    r"\b([A-Za-z_][A-Za-z0-9_.]*Id)\b\s*(=|!=)\s*['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)
DEEP_RELATIONSHIP_PATH_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*){2,}\b")
NON_FILTERABLE_OBJECT_FIELDS = {
    "Account": {"Description"},
    "Case": {"Description"},
    "EmailMessage": {"TextBody"},
    "Issue__c": {"Description__c"},
    "Knowledge__kav": {"FAQ_Answer__c"},
    "LiveChatTranscript": {"Body"},
    "Opportunity": {"Description"},
    "VoiceCallTranscript__c": {"Body__c"},
}
SOSL_NON_SEARCHABLE_OBJECTS = {"Issue__c"}
SUPPORTED_SOSL_FIELD_GROUPS = {
    "ALL FIELDS",
    "NAME FIELDS",
    "EMAIL FIELDS",
    "PHONE FIELDS",
    "SIDEBAR FIELDS",
}
AGGREGATE_FUNCTIONS = {"COUNT", "COUNT_DISTINCT", "SUM", "AVG", "MIN", "MAX"}
DATETIME_FIELD_NAMES = {
    "CreatedDate",
    "ClosedDate",
    "EndTime",
    "EndTime__c",
    "MessageDate",
    "StartDateTime",
}
DATE_FIELD_NAMES = {
    "ActivityDate",
    "CloseDate",
    "CompanySignedDate",
    "ConvertedDate",
    "CustomerSignedDate",
    "EffectiveDate",
    "ExpirationDate",
    "StartDate",
    "ValidFrom",
    "ValidTo",
}
KNOWN_STANDARD_OBJECT_FIELDS = {
    "Account": {"AnnualRevenue", "OwnerId"},
    "Contact": {"Name", "Phone", "Title"},
    "Event": {"WhoId"},
    "LiveChatTranscript": {"Body", "CreatedDate", "EndTime", "LeadId__c", "OwnerId"},
    "OpportunityLineItem": {"UnitPrice"},
    "Order": {"CreatedDate", "Name"},
    "PricebookEntry": {"IsActive", "Name"},
    "Quote": {"OwnerId", "Pricebook2Id"},
    "Task": {"WhoId"},
    "User": {"IsActive", "Title"},
    "VoiceCallTranscript__c": {"OwnerId"},
}
KNOWN_SCHEMA_OMITTED_OBJECT_FIELDS = {
    "Profile": {"Id", "Name", "Description"},
}


class ActionVerifier:
    def __init__(self, schema_index: SchemaIndex) -> None:
        self.schema_index = schema_index

    @classmethod
    def from_schema(cls, schema_obj: Iterable[Mapping]) -> "ActionVerifier":
        return cls(build_schema_index(schema_obj))

    def verify_action(
        self,
        action: Optional[Mapping],
        failed_queries: Optional[Iterable[str]] = None,
    ) -> VerificationResult:
        if not action:
            return self._invalid("EMPTY_ACTION", "No structured action was parsed. Use <execute>query</execute> or <respond>answer</respond>.")

        action_name = str(action.get("name", "")).strip().lower()
        content = str(action.get("content", "")).strip()

        if action_name not in {"execute", "respond"}:
            return self._invalid("UNKNOWN_ACTION", "Unsupported action. Use only execute or respond.")
        if not content:
            return self._invalid("EMPTY_ACTION", f"The {action_name} action content is empty.")

        if action_name == "execute":
            return self._verify_execute(content, failed_queries or [])
        return self._verify_respond(content)

    def _verify_execute(self, query: str, failed_queries: Iterable[str]) -> VerificationResult:
        quote_error = self._balanced_quotes(query)
        if quote_error:
            return quote_error
        if not self._balanced_parentheses(query):
            return self._invalid("UNBALANCED_PARENTHESES", "The query has unbalanced parentheses. Return exactly one complete SOQL/SOSL query.")

        stripped_literals = self._strip_string_literals(query)
        if not READ_ONLY_START_RE.match(stripped_literals):
            return self._invalid("INVALID_QUERY_TYPE", "Only read-only SOQL/SOSL is allowed. Start the query with SELECT or FIND.")
        query_for_admin_check = stripped_literals
        if stripped_literals.lstrip().lower().startswith("find"):
            query_for_admin_check = self._strip_sosl_search_terms(stripped_literals)
        if WRITE_OR_ADMIN_RE.search(query_for_admin_check):
            return self._invalid("INVALID_QUERY_TYPE", "Write or administrative Salesforce operations are not allowed. Use only read-only SELECT or FIND queries.")

        normalized_failed = {normalize_query(item) for item in failed_queries}
        if normalize_query(query) in normalized_failed:
            return self._invalid("REPEATED_FAILED_QUERY", "This exact query already failed. Change the query before trying again.")

        if stripped_literals.lstrip().lower().startswith("select"):
            return self._verify_soql(query, stripped_literals)
        return self._verify_sosl(query, stripped_literals)

    def _strip_sosl_search_terms(self, query: str) -> str:
        return re.sub(r"\bfind\s*\{[^}]*\}", "FIND {}", query, flags=re.IGNORECASE | re.DOTALL)

    def _verify_respond(self, content: str) -> VerificationResult:
        stripped_literals = self._strip_string_literals(content)
        if READ_ONLY_START_RE.match(stripped_literals):
            return self._invalid("INVALID_RESPONSE_FORMAT", "The respond action looks like a Salesforce query. Use execute for queries or respond with the final answer only.")
        return VerificationResult(valid=True)

    def _verify_soql(self, query: str, stripped_literals: str) -> VerificationResult:
        parse_result = parse_soql(query)
        grammar_error = self._verify_official_soql_grammar(parse_result)
        if grammar_error:
            return grammar_error

        top_level_objects = self._extract_parser_top_level_soql_objects(parse_result)
        if not top_level_objects:
            top_level_objects = self._extract_top_level_soql_objects(stripped_literals)
        if not top_level_objects:
            return self._invalid("INVALID_QUERY_TYPE", "SOQL must include FROM followed by a Salesforce object from the schema.")
        object_name = top_level_objects[0]
        if not self._object_exists(object_name):
            return self._invalid("UNKNOWN_OBJECT", f"Unknown Salesforce object '{object_name}'. Use only objects listed in the schema.")

        syntax_error = self._verify_salesforce_soql_syntax(query, stripped_literals, object_name)
        if syntax_error:
            return syntax_error

        relationship_error = self._verify_soql_relationships(stripped_literals, object_name)
        if relationship_error:
            return relationship_error

        group_by_error = self._verify_group_by_sanity(parse_result)
        if group_by_error:
            return group_by_error

        for other_object in top_level_objects:
            if other_object == object_name:
                continue
            if self._looks_like_relationship_name(other_object):
                continue
            if not self._object_exists(other_object):
                return self._invalid("UNKNOWN_OBJECT", f"Unknown Salesforce object '{other_object}'. Use only objects listed in the schema.")

        fields = self._extract_soql_fields(stripped_literals, object_name)
        for field in fields:
            if not self._field_exists(object_name, field):
                return self._unknown_field_result(object_name, field)

        return VerificationResult(valid=True)

    def _verify_sosl(self, query: str, stripped_literals: str) -> VerificationResult:
        sosl_error = self._verify_salesforce_sosl_syntax(query)
        if sosl_error:
            return sosl_error

        for object_name, fields in self._extract_sosl_returning(stripped_literals):
            if object_name in SOSL_NON_SEARCHABLE_OBJECTS:
                return self._invalid("UNSEARCHABLE_SOSL_OBJECT", f"Object '{object_name}' is not searchable with SOSL in this benchmark. Query it with SOQL instead.")
            if not self._object_exists(object_name):
                return self._invalid("UNKNOWN_OBJECT", f"Unknown Salesforce object '{object_name}'. Use only objects listed in the schema.")
            for field in fields:
                if not self._field_exists(object_name, field):
                    return self._unknown_field_result(object_name, field)
        return VerificationResult(valid=True)

    def _extract_soql_objects(self, query: str) -> List[str]:
        return [match.group(1) for match in re.finditer(r"\bfrom\s+([A-Za-z_][A-Za-z0-9_]*)\b", query, re.IGNORECASE)]

    def _extract_top_level_soql_objects(self, query: str) -> List[str]:
        objects = []
        depth = 0
        in_quote = None
        escaped = False
        idx = 0
        while idx < len(query):
            char = query[idx]
            if escaped:
                escaped = False
                idx += 1
                continue
            if char == "\\":
                escaped = True
                idx += 1
                continue
            if in_quote:
                if char == in_quote:
                    in_quote = None
                idx += 1
                continue
            if char in {"'", '"'}:
                in_quote = char
                idx += 1
                continue
            if char == "(":
                depth += 1
                idx += 1
                continue
            if char == ")":
                depth = max(0, depth - 1)
                idx += 1
                continue
            if depth == 0:
                match = re.match(r"\bfrom\s+([A-Za-z_][A-Za-z0-9_]*)\b", query[idx:], re.IGNORECASE)
                if match:
                    objects.append(match.group(1))
                    idx += match.end()
                    continue
            idx += 1
        return objects

    def _parser_tokens(self, parse_result: SOQLParseResult) -> List[Mapping]:
        return [
            token
            for token in parse_result.tokens
            if token.get("text") and token.get("text") != "<EOF>"
        ]

    def _extract_parser_top_level_soql_objects(self, parse_result: SOQLParseResult) -> List[str]:
        if parse_result.unavailable or not parse_result.success:
            return []
        tokens = self._parser_tokens(parse_result)
        from_index = self._top_level_keyword_index(tokens, ("FROM",))
        if from_index is None:
            return []
        if from_index + 1 >= len(tokens):
            return []
        object_token = tokens[from_index + 1].get("text", "")
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:__c)?", str(object_token)):
            return [str(object_token)]
        return []

    def _top_level_keyword_index(self, tokens: Sequence[Mapping], keywords: Sequence[str]) -> Optional[int]:
        target = tuple(keyword.upper() for keyword in keywords)
        depth = 0
        idx = 0
        while idx < len(tokens):
            text = str(tokens[idx].get("text", ""))
            if text == "(":
                depth += 1
            elif text == ")":
                depth = max(0, depth - 1)
            elif depth == 0:
                current = tuple(str(token.get("text", "")).upper() for token in tokens[idx : idx + len(target)])
                if current == target:
                    return idx
            idx += 1
        return None

    def _top_level_clause_tokens(
        self,
        tokens: Sequence[Mapping],
        start_keywords: Sequence[str],
        stop_keywords: Sequence[Sequence[str]],
    ) -> List[Mapping]:
        start = self._top_level_keyword_index(tokens, start_keywords)
        if start is None:
            return []
        clause_start = start + len(start_keywords)
        clause_end = len(tokens)
        for stop in stop_keywords:
            stop_index = self._top_level_keyword_index(tokens[clause_start:], stop)
            if stop_index is not None:
                clause_end = min(clause_end, clause_start + stop_index)
        return list(tokens[clause_start:clause_end])

    def _parser_select_expressions(self, parse_result: SOQLParseResult) -> List[str]:
        tokens = self._parser_tokens(parse_result)
        expr_tokens = self._top_level_clause_tokens(
            tokens,
            ("SELECT",),
            (("FROM",),),
        )
        return self._split_token_expressions(expr_tokens)

    def _parser_group_by_expressions(self, parse_result: SOQLParseResult) -> List[str]:
        tokens = self._parser_tokens(parse_result)
        expr_tokens = self._top_level_clause_tokens(
            tokens,
            ("GROUP", "BY"),
            (("HAVING",), ("ORDER", "BY"), ("LIMIT",), ("OFFSET",)),
        )
        return self._split_token_expressions(expr_tokens)

    def _split_token_expressions(self, tokens: Sequence[Mapping]) -> List[str]:
        expressions: List[List[Mapping]] = [[]]
        depth = 0
        for token in tokens:
            text = str(token.get("text", ""))
            if text == "(":
                depth += 1
            elif text == ")":
                depth = max(0, depth - 1)
            if text == "," and depth == 0:
                expressions.append([])
                continue
            expressions[-1].append(token)
        return [
            self._normalize_expression_text(self._join_token_text(expression))
            for expression in expressions
            if self._join_token_text(expression).strip()
        ]

    def _join_token_text(self, tokens: Sequence[Mapping]) -> str:
        pieces: List[str] = []
        previous = ""
        for token in tokens:
            text = str(token.get("text", ""))
            if not text:
                continue
            if text in {",", ")", "."}:
                pieces.append(text)
            elif previous in {"(", "."}:
                pieces.append(text)
            elif text == "(":
                pieces.append(text)
            else:
                if pieces:
                    pieces.append(" ")
                pieces.append(text)
            previous = text
        return "".join(pieces).strip()

    def _normalize_expression_text(self, expression: str) -> str:
        expression = re.sub(r"\s+", " ", expression.strip())
        expression = re.sub(r"\s+([(),.])", r"\1", expression)
        expression = re.sub(r"([(.])\s+", r"\1", expression)
        return expression

    def _extract_soql_fields(self, query: str, object_name: str) -> Set[str]:
        fields: Set[str] = set()
        select_text = self._top_level_select_text(query)
        if select_text:
            for expression in self._split_top_level(select_text, ","):
                if self._is_child_subquery_expression(expression):
                    continue
                fields.update(self._fields_from_expression(expression))

        for clause_name in ("where", "having"):
            clause = self._extract_clause(query, clause_name, ("group by", "order by", "limit", "offset", "having"))
            fields.update(self._fields_from_conditions(clause))

        for clause_name in ("group by", "order by"):
            clause = self._extract_clause(query, clause_name, ("limit", "offset", "having"))
            for expression in self._split_top_level(clause, ","):
                fields.update(self._fields_from_expression(expression))
        return fields

    def _extract_sosl_returning(self, query: str) -> List[Tuple[str, Set[str]]]:
        returning_match = re.search(r"\breturning\s+(.+)$", query, re.IGNORECASE | re.DOTALL)
        if not returning_match:
            return []
        entries = []
        for object_part in self._split_top_level(returning_match.group(1), ","):
            match = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:\((.*?)\))?", object_part, re.IGNORECASE | re.DOTALL)
            if not match:
                continue
            object_name = match.group(1)
            field_text = match.group(2) or ""
            fields = set()
            for expression in self._split_top_level(field_text, ","):
                fields.update(self._fields_from_expression(expression))
            entries.append((object_name, fields))
        return entries

    def _top_level_select_text(self, query: str) -> str:
        span = self._top_level_select_span(query)
        if not span:
            return ""
        start, end = span
        return query[start:end].strip()

    def _top_level_select_span(self, query: str) -> Optional[Tuple[int, int]]:
        select_match = re.match(r"\s*select\b", query, re.IGNORECASE)
        if not select_match:
            return None
        start = select_match.end()
        depth = 0
        in_quote = None
        escaped = False
        idx = start
        while idx < len(query):
            char = query[idx]
            if escaped:
                escaped = False
                idx += 1
                continue
            if char == "\\":
                escaped = True
                idx += 1
                continue
            if in_quote:
                if char == in_quote:
                    in_quote = None
                idx += 1
                continue
            if char in {"'", '"'}:
                in_quote = char
                idx += 1
                continue
            if char == "(":
                depth += 1
                idx += 1
                continue
            if char == ")":
                depth = max(0, depth - 1)
                idx += 1
                continue
            if depth == 0 and re.match(r"\bfrom\b", query[idx:], re.IGNORECASE):
                return start, idx
            idx += 1
        return None

    def _extract_clause(self, query: str, clause_name: str, stop_clauses: Sequence[str]) -> str:
        start = re.search(rf"\b{re.escape(clause_name)}\b", query, re.IGNORECASE)
        if not start:
            return ""
        clause_start = start.end()
        clause_end = len(query)
        for stop_clause in stop_clauses:
            if stop_clause.lower() == clause_name.lower():
                continue
            stop = re.search(rf"\b{re.escape(stop_clause)}\b", query[clause_start:], re.IGNORECASE)
            if stop:
                clause_end = min(clause_end, clause_start + stop.start())
        return query[clause_start:clause_end]

    def _fields_from_conditions(self, clause: str) -> Set[str]:
        fields = set()
        pattern = re.compile(
            r"\b([A-Za-z_][A-Za-z0-9_.]*)\b\s*(?:=|!=|<=|>=|<|>|\blike\b|\bin\b|\bincludes\b|\bexcludes\b)",
            re.IGNORECASE,
        )
        for match in pattern.finditer(clause):
            if re.search(r"\bselect\b", clause[: match.start()], re.IGNORECASE):
                continue
            fields.update(self._fields_from_expression(match.group(1)))
        return fields

    def _fields_from_expression(self, expression: str) -> Set[str]:
        expression = expression.strip()
        expression = re.sub(r"\s+as\s+[A-Za-z_][A-Za-z0-9_]*\s*$", "", expression, flags=re.IGNORECASE)
        if ")" in expression:
            expression = re.sub(r"\s+[A-Za-z_][A-Za-z0-9_]*\s*$", "", expression)
        if not expression or expression == "*":
            return set()
        fields = set()
        if "." in expression:
            # Relationship paths are valid Salesforce syntax, but the compact
            # benchmark schema does not reliably describe relationship names.
            return fields
        for token in IDENT_RE.findall(expression):
            upper = token.upper()
            if upper in SOQL_KEYWORDS:
                continue
            if token.isdigit():
                continue
            if "." in token:
                # Relationship fields are not represented uniformly in the benchmark schema.
                continue
            fields.add(token)
        return fields

    def _verify_soql_relationships(self, query: str, object_name: str) -> Optional[VerificationResult]:
        for relationship_name, fields, relationship_refs in self._extract_child_subqueries(query):
            child_object = self.schema_index.child_relationship_object(object_name, relationship_name)
            if not child_object:
                return self._unknown(
                    "UNKNOWN_RELATIONSHIP",
                    (
                        f"Child relationship '{relationship_name}' from object '{object_name}' is not present in trusted schema metadata. "
                        "Allowing execution because the relationship may be org-specific or omitted from the compact benchmark schema."
                    ),
                    rule="relationship_validation",
                )
            if not self._object_exists(child_object):
                return self._invalid("UNKNOWN_OBJECT", f"Unknown Salesforce object '{child_object}'. Use only objects listed in the schema.")
            for field in fields:
                if not self._field_exists(child_object, field):
                    return self._unknown_field_result(child_object, field, context=f"child relationship '{relationship_name}'")
            child_relationship_error = self._verify_relationship_field_refs(relationship_refs, child_object)
            if child_relationship_error:
                return child_relationship_error

        parent_query = self._query_without_child_subqueries(query)
        relationship_error = self._verify_relationship_field_refs(
            self._extract_relationship_field_refs(parent_query, object_name),
            object_name,
        )
        if relationship_error:
            return relationship_error

        semijoin_error = self._verify_semijoin_relationships(query, object_name)
        if semijoin_error:
            return semijoin_error
        return None

    def _extract_child_subqueries(self, query: str) -> List[Tuple[str, Set[str], Set[Tuple[str, str]]]]:
        subqueries = []
        pattern = re.compile(
            r"^\(\s*select\s+(.+?)\s+from\s+([A-Za-z_][A-Za-z0-9_]*(?:__r)?)\b",
            re.IGNORECASE | re.DOTALL,
        )
        for subquery in self._child_subquery_expressions(query):
            match = pattern.search(subquery)
            if not match:
                continue
            field_text = match.group(1)
            relationship_name = match.group(2)
            fields = set()
            for expression in self._split_top_level(field_text, ","):
                fields.update(self._fields_from_expression(expression))
            relationship_refs = self._extract_relationship_field_refs(field_text)
            subqueries.append((relationship_name, fields, relationship_refs))
        return subqueries

    def _is_child_subquery_expression(self, expression: str) -> bool:
        return bool(re.match(r"^\(?\s*select\b", expression.strip(), re.IGNORECASE))

    def _extract_relationship_field_refs(self, query: str, object_name: Optional[str] = None) -> Set[Tuple[str, str]]:
        refs: Set[Tuple[str, str]] = set()
        for match in re.finditer(
            r"\b([A-Za-z_][A-Za-z0-9_]*(?:__r)?)\.([A-Za-z_][A-Za-z0-9_]*(?:__c)?)\b",
            query,
            re.IGNORECASE,
        ):
            relationship_name = match.group(1)
            field_name = match.group(2)
            if object_name and relationship_name == object_name:
                continue
            if relationship_name.upper() in SOQL_KEYWORDS or field_name.upper() in SOQL_KEYWORDS:
                continue
            refs.add((relationship_name, field_name))
        return refs

    def _verify_relationship_field_refs(
        self,
        refs: Iterable[Tuple[str, str]],
        object_name: str,
    ) -> Optional[VerificationResult]:
        for relationship_name, field_name in refs:
            targets = self.schema_index.parent_relationship_objects(object_name, relationship_name)
            if not targets:
                return self._unknown(
                    "UNKNOWN_RELATIONSHIP",
                    (
                        f"Parent relationship '{relationship_name}' from object '{object_name}' is not present in trusted schema metadata. "
                        "Allowing execution because the relationship may be org-specific or omitted from the compact benchmark schema."
                    ),
                    rule="relationship_validation",
                )
            if not any(self._field_exists(target, field_name) for target in targets):
                target_text = "/".join(sorted(targets))
                if len(targets) == 1:
                    return self._unknown_field_result(next(iter(targets)), field_name, context=f"relationship '{relationship_name}'")
                suggestions = []
                for target in sorted(targets):
                    suggestions.extend(self._field_suggestions(target, field_name, limit=3))
                suggestion_text = self._format_field_suggestions(suggestions[:6])
                return self._invalid(
                    "UNKNOWN_FIELD",
                    (
                        f"Unknown field '{field_name}' on related object '{target_text}' through relationship '{relationship_name}'. "
                        "Use only fields listed for the related object in the benchmark schema."
                        f"{suggestion_text}"
                    ),
                )
        return None

    def _child_subquery_expressions(self, query: str) -> List[str]:
        select_text = self._top_level_select_text(query)
        subqueries = []
        idx = 0
        while idx < len(select_text):
            if select_text[idx] != "(" or not re.match(r"\(\s*select\b", select_text[idx:], re.IGNORECASE):
                idx += 1
                continue
            end = self._matching_parenthesis_index(select_text, idx)
            if end is None:
                idx += 1
                continue
            subqueries.append(select_text[idx : end + 1])
            idx = end + 1
        return subqueries

    def _query_without_child_subqueries(self, query: str) -> str:
        span = self._top_level_select_span(query)
        if not span:
            return query
        start, end = span
        select_text = query[start:end]
        chars = list(select_text)
        idx = 0
        while idx < len(chars):
            if chars[idx] != "(" or not re.match(r"\(\s*select\b", "".join(chars[idx:]), re.IGNORECASE):
                idx += 1
                continue
            subquery_end = self._matching_parenthesis_index(select_text, idx)
            if subquery_end is None:
                idx += 1
                continue
            for replace_idx in range(idx, subquery_end + 1):
                chars[replace_idx] = " "
            idx = subquery_end + 1
        return f"{query[:start]}{''.join(chars)}{query[end:]}"

    def _matching_parenthesis_index(self, text: str, open_index: int) -> Optional[int]:
        depth = 0
        in_quote = None
        escaped = False
        for idx in range(open_index, len(text)):
            char = text[idx]
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if in_quote:
                if char == in_quote:
                    in_quote = None
                continue
            if char in {"'", '"'}:
                in_quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    return idx
        return None

    def _verify_semijoin_relationships(self, query: str, object_name: str) -> Optional[VerificationResult]:
        semijoin_re = re.compile(
            r"\b([A-Za-z_][A-Za-z0-9_.]*(?:__c)?)\b\s+(?:not\s+)?in\s*\(\s*select\s+([A-Za-z_][A-Za-z0-9_.]*(?:__c)?)\s+from\s+([A-Za-z_][A-Za-z0-9_]*(?:__c)?)\b",
            re.IGNORECASE | re.DOTALL,
        )
        for match in semijoin_re.finditer(query):
            outer_field = match.group(1)
            selected_field = match.group(2)
            subquery_object = match.group(3)
            if not self._object_exists(subquery_object):
                return self._invalid("UNKNOWN_OBJECT", f"Unknown Salesforce object '{subquery_object}'. Use only objects listed in the schema.")

            selected_leaf = selected_field.split(".")[-1]
            if not self._field_exists(subquery_object, selected_leaf):
                return self._unknown_field_result(subquery_object, selected_leaf)

            outer_types = self._field_entity_types(object_name, outer_field)
            selected_types = self._field_entity_types(subquery_object, selected_field)
            if outer_types and selected_types and outer_types.isdisjoint(selected_types):
                return self._invalid(
                    "INVALID_RELATIONSHIP",
                    f"Semi-join compares incompatible relationship targets: '{outer_field}' does not reference records returned by '{selected_field} FROM {subquery_object}'.",
                )
        return None

    def _field_entity_types(self, object_name: str, field_expression: str) -> Set[str]:
        parts = field_expression.split(".")
        if len(parts) == 1:
            field_name = parts[0]
            if field_name == "Id":
                return {object_name}
            return self.schema_index.referenced_objects(object_name, field_name)
        if len(parts) == 2:
            relationship_name, field_name = parts
            targets = self.schema_index.parent_relationship_objects(object_name, relationship_name)
            entity_types: Set[str] = set()
            for target in targets:
                if field_name == "Id":
                    entity_types.add(target)
                else:
                    entity_types.update(self.schema_index.referenced_objects(target, field_name))
            return entity_types
        return set()

    def _verify_salesforce_soql_syntax(self, query: str, stripped_literals: str, object_name: str) -> Optional[VerificationResult]:
        if SQL_ONLY_CONSTRUCT_RE.search(stripped_literals):
            return self._invalid("INVALID_SOQL_SYNTAX", "SQL JOIN/UNION syntax is not valid SOQL in this benchmark.")
        if SCALAR_SUBQUERY_RE.search(stripped_literals):
            return self._invalid("UNSUPPORTED_SEMIJOIN", "SOQL does not support scalar subqueries such as '= (SELECT ...)'. Use an IN semi-join when valid.")
        if AS_ALIAS_RE.search(stripped_literals):
            return self._invalid("INVALID_SOQL_SYNTAX", "SOQL aliases using AS are not supported in this benchmark. Use a bare alias or omit the alias.")
        if SQL_DATE_LITERAL_RE.search(query):
            return self._invalid("INVALID_DATE_LITERAL", "SQL DATE 'YYYY-MM-DD' literal syntax is not valid SOQL in this benchmark. Use an unquoted Salesforce date/dateTime literal.")
        if SELECT_DISTINCT_RE.search(stripped_literals):
            return self._invalid("INVALID_SOQL_SYNTAX", "SELECT DISTINCT is not valid SOQL in this benchmark. Use COUNT_DISTINCT where appropriate or query fields directly.")
        if ORDER_BY_AGGREGATE_ARITHMETIC_RE.search(stripped_literals):
            return self._invalid("INVALID_SOQL_SYNTAX", "Arithmetic over aggregate expressions in ORDER BY is not valid SOQL in this benchmark.")
        if DEEP_RELATIONSHIP_PATH_RE.search(stripped_literals):
            return self._invalid("INVALID_SOQL_SYNTAX", "Deep relationship traversal is not valid in this SOQL context. Query relationship IDs first, then query related records separately.")
        if SQL_CONDITIONAL_AGG_RE.search(stripped_literals):
            return self._invalid("INVALID_SOQL_SYNTAX", "SQL CASE/COUNTIF style conditional aggregation is not valid SOQL in this benchmark.")
        if EMPTY_COUNT_RE.search(query) and not self._is_simple_count_query(stripped_literals):
            return self._invalid("INVALID_SOQL_SYNTAX", "SOQL COUNT() is only allowed as the sole selected expression. Use COUNT(Id) when grouping or selecting other fields.")
        if SQL_FUNCTION_RE.search(stripped_literals):
            return self._invalid("INVALID_SOQL_SYNTAX", "SQL date/time functions such as DATEDIFF are not valid SOQL in this benchmark.")
        if UNSUPPORTED_DATE_FUNCTION_RE.search(stripped_literals):
            return self._invalid("UNSUPPORTED_DATE_FUNCTION", "DATEVALUE(...) filters are rejected by the benchmark Salesforce environment. Use an unquoted date or datetime literal appropriate for the field type.")
        if ARITHMETIC_EXPRESSION_RE.search(stripped_literals):
            return self._invalid("INVALID_SOQL_SYNTAX", "Arithmetic expressions over fields are not valid SOQL in this benchmark. Query raw fields and compute outside SOQL.")
        date_error = self._verify_date_literals(query, object_name)
        if date_error:
            return date_error
        id_error = self._verify_id_literals(query)
        if id_error:
            return id_error
        non_filterable = self._non_filterable_text_field(query, object_name)
        if non_filterable:
            return self._invalid("NON_FILTERABLE_FIELD", f"Field '{non_filterable}' exists but cannot be used in a SOQL filter. Use SOSL or filter on another field.")
        if self._has_semijoin_with_or(stripped_literals):
            return self._invalid("UNSUPPORTED_SEMIJOIN", "Salesforce does not support semi-join subqueries combined with OR in this benchmark.")
        if self._has_nested_semijoin(stripped_literals):
            return self._invalid("UNSUPPORTED_SEMIJOIN", "Nested semi-join subqueries are not supported by Salesforce in this benchmark.")
        return None

    def _verify_official_soql_grammar(self, result: SOQLParseResult) -> Optional[VerificationResult]:
        if result.unavailable or result.success:
            return None
        return self._invalid("INVALID_SOQL_GRAMMAR", self._format_parser_feedback(result))

    def _format_parser_feedback(self, result: SOQLParseResult) -> str:
        if not result.errors:
            return "The official SOQL parser rejected this query. Return one grammatically valid SOQL query."
        error = result.errors[0]
        location = ""
        if error.line is not None and error.column is not None:
            location = f" at line {error.line}, column {error.column}"
        token = ""
        if error.token and error.token.get("text"):
            token = f" near token '{error.token.get('text')}'"
        return (
            "The official SOQL parser rejected this query"
            f"{location}{token}: {error.message}. "
            "Return one grammatically valid SOQL query."
        )

    def _verify_group_by_sanity(self, parse_result: SOQLParseResult) -> Optional[VerificationResult]:
        if parse_result.unavailable or not parse_result.success:
            return None
        group_expressions = self._parser_group_by_expressions(parse_result)
        if not group_expressions:
            return None
        group_set = {self._canonical_expression(expression) for expression in group_expressions}
        for expression in self._parser_select_expressions(parse_result):
            if self._is_aggregate_expression(expression):
                continue
            canonical = self._canonical_expression(self._strip_select_alias(expression))
            if canonical in group_set:
                continue
            if self._is_plain_field_expression(canonical):
                return self._invalid(
                    "UNGROUPED_SELECTED_FIELD",
                    (
                        f"Selected field '{expression}' is not included in GROUP BY and is not aggregated. "
                        "When using GROUP BY, select only grouped fields or aggregate expressions."
                    ),
                )
            return self._unknown(
                "UNKNOWN_GROUP_BY_EXPRESSION",
                (
                    f"The verifier could not confidently classify grouped SELECT expression '{expression}'. "
                    "Allowing execution because the official parser accepted the query."
                ),
                rule="group_by_validation",
            )
        return None

    def _is_aggregate_expression(self, expression: str) -> bool:
        return bool(
            re.match(
                rf"^\s*(?:{'|'.join(sorted(AGGREGATE_FUNCTIONS))})\s*\(",
                expression,
                re.IGNORECASE,
            )
        )

    def _strip_select_alias(self, expression: str) -> str:
        if self._is_aggregate_expression(expression):
            return expression
        parts = expression.strip().split()
        if len(parts) == 2 and self._is_plain_field_expression(self._canonical_expression(parts[0])):
            return parts[0]
        return expression.strip()

    def _canonical_expression(self, expression: str) -> str:
        return re.sub(r"\s+", "", expression).lower()

    def _is_plain_field_expression(self, expression: str) -> bool:
        return bool(re.fullmatch(r"[a-z_][a-z0-9_]*(?:__(?:c|r))?(?:\.[a-z_][a-z0-9_]*(?:__(?:c|r))?)*", expression))

    def _verify_id_literals(self, query: str) -> Optional[VerificationResult]:
        for match in ID_LITERAL_COMPARISON_RE.finditer(query):
            field_name = match.group(1).split(".")[-1]
            literal = match.group(3)
            if literal.upper() == "NULL":
                continue
            if len(literal) not in {15, 18} or not literal.isalnum():
                return self._invalid("INVALID_ID_LITERAL", f"Field '{field_name}' expects a 15- or 18-character Salesforce ID literal, not a label or name.")
        return None

    def _verify_salesforce_sosl_syntax(self, query: str) -> Optional[VerificationResult]:
        if not self._balanced_sosl_search_braces(query):
            return self._invalid("UNBALANCED_SEARCH_BRACES", "The SOSL FIND search term must use one balanced pair of braces, for example FIND {Smith}.")
        search_match = re.search(r"\bfind\s*\{([^}]*)\}", query, re.IGNORECASE | re.DOTALL)
        if not search_match:
            return self._invalid("INVALID_QUERY_TYPE", "SOSL must start with FIND followed by a braced search term, for example FIND {Smith}.")
        search_terms = search_match.group(1)
        if not search_terms.strip():
            return self._invalid("EMPTY_SOSL_SEARCH_TERM", "The SOSL FIND search term is empty. Put the search text inside FIND {...}.")
        field_group_match = re.search(r"\bin\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)\s+fields\b", query, re.IGNORECASE)
        if field_group_match:
            field_group = f"{field_group_match.group(1).upper()} FIELDS"
            field_group = re.sub(r"\s+", " ", field_group)
            if field_group not in SUPPORTED_SOSL_FIELD_GROUPS:
                supported = ", ".join(sorted(SUPPORTED_SOSL_FIELD_GROUPS))
                return self._invalid(
                    "UNSUPPORTED_SOSL_FIELD_GROUP",
                    (
                        f"SOSL field group '{field_group}' is not supported here. "
                        f"Use one of: {supported}; or use SOQL when filtering a specific field."
                    ),
                )
        if re.search(r"\breturning\b", query, re.IGNORECASE) and not self._extract_sosl_returning(query):
            return self._invalid("MALFORMED_SOSL_RETURNING", "SOSL RETURNING must name one or more objects, optionally with field lists such as RETURNING Contact(Id, Name).")
        if re.search(r"(?<=\w)-(?:\w)", search_terms):
            return self._invalid("INVALID_SOSL_SEARCH_TERM", "SOSL search terms with embedded hyphens are rejected by Salesforce here. Use separate terms or quote/escape carefully.")
        return None

    def _balanced_sosl_search_braces(self, query: str) -> bool:
        find_match = re.search(r"\bfind\b", query, re.IGNORECASE)
        if not find_match:
            return True
        after_find = query[find_match.end():]
        return after_find.count("{") == 1 and after_find.count("}") == 1 and after_find.find("{") < after_find.find("}")

    def _verify_date_literals(self, query: str, object_name: str) -> Optional[VerificationResult]:
        for match in DATE_COMPARISON_RE.finditer(query):
            field_name = match.group(1).split(".")[-1]
            literal = match.group(3)
            temporal_type = self._temporal_field_type(object_name, field_name)
            if not temporal_type:
                continue
            quoted = literal.startswith(("'", '"')) and literal.endswith(("'", '"'))
            raw_literal = literal.strip("'\"")
            has_time = "T" in raw_literal
            if quoted:
                return self._invalid("INVALID_DATE_LITERAL", f"Field '{field_name}' is a Salesforce {temporal_type} field. Date/dateTime filter literals must not be quoted.")
            if temporal_type == "datetime" and not has_time:
                return self._invalid("INVALID_DATE_LITERAL", f"Field '{field_name}' expects an unquoted datetime literal like YYYY-MM-DDTHH:MM:SSZ.")
            if temporal_type == "date" and has_time:
                return self._invalid("INVALID_DATE_LITERAL", f"Field '{field_name}' expects an unquoted date literal like YYYY-MM-DD, not a datetime literal.")
        return None

    def _temporal_field_type(self, object_name: str, field_name: str) -> Optional[str]:
        description = self.schema_index.field_description(object_name, field_name).lower()
        if "yyyy-mm-ddthh:mm:ss" in description or "timestamp" in description or "datetime" in description:
            return "datetime"
        if "yyyy-mm-dd" in description:
            return "date"
        if field_name in DATETIME_FIELD_NAMES:
            return "datetime"
        if field_name in DATE_FIELD_NAMES:
            return "date"
        return None

    def _non_filterable_text_field(self, query: str, object_name: str) -> Optional[str]:
        for field_name in sorted(NON_FILTERABLE_OBJECT_FIELDS.get(object_name, set())):
            pattern = rf"\b{re.escape(field_name)}\b\s*(?:=|!=|<=|>=|<|>|\blike\b|\bin\b|\bincludes\b|\bexcludes\b)"
            if re.search(pattern, query, re.IGNORECASE):
                return field_name
        return None

    def _has_semijoin_with_or(self, query: str) -> bool:
        top_level_where = self._top_level_where_clause(query)
        return bool(re.search(r"\bor\b[^()]*\bin\s*\(\s*select\b|\bin\s*\(\s*select\b[^()]*\)\s*\bor\b", top_level_where, re.IGNORECASE | re.DOTALL))

    def _has_nested_semijoin(self, query: str) -> bool:
        for match in re.finditer(r"\bin\s*\(\s*select\b", query, re.IGNORECASE):
            remainder = query[match.end():]
            if re.search(r"\bin\s*\(\s*select\b", remainder, re.IGNORECASE):
                return True
        return False

    def _looks_like_relationship_name(self, object_name: str) -> bool:
        return (
            object_name.endswith("Items")
            or object_name.endswith("Histories")
            or object_name.endswith("LineItems")
            or object_name.endswith("__r")
        )

    def _top_level_where_clause(self, query: str) -> str:
        return self._extract_clause(query, "where", ("group by", "order by", "limit", "offset", "having"))

    def _object_exists(self, object_name: str) -> bool:
        return self.schema_index.has_object(object_name) or object_name in KNOWN_SCHEMA_OMITTED_OBJECT_FIELDS

    def _is_simple_count_query(self, query: str) -> bool:
        select_match = re.search(r"\bselect\s+(.+?)\s+\bfrom\b", query, re.IGNORECASE | re.DOTALL)
        if not select_match:
            return False
        select_text = select_match.group(1).strip()
        return bool(re.fullmatch(r"COUNT\s*\(\s*\)", select_text, re.IGNORECASE))

    def _field_exists(self, object_name: str, field_name: str) -> bool:
        if self.schema_index.has_field(object_name, field_name):
            return True
        if field_name in KNOWN_STANDARD_OBJECT_FIELDS.get(object_name, set()):
            return True
        if field_name in KNOWN_SCHEMA_OMITTED_OBJECT_FIELDS.get(object_name, set()):
            return True
        # Aggregate aliases and Salesforce pseudo-fields are commonly omitted from compact schemas.
        if field_name.lower().startswith("expr"):
            return True
        return False

    def _unknown_field_result(self, object_name: str, field_name: str, context: Optional[str] = None) -> VerificationResult:
        location = f"object '{object_name}'"
        if context:
            location = f"{context} ({object_name})"
        return self._invalid(
            "UNKNOWN_FIELD",
            (
                f"Unknown field '{field_name}' on {location}. "
                "Use only fields listed for that object in the benchmark schema."
                f"{self._format_field_suggestions(self._field_suggestions(object_name, field_name))}"
            ),
        )

    def _field_suggestions(self, object_name: str, field_name: str, limit: int = 6) -> List[str]:
        available = set(self.schema_index.object_fields.get(object_name, set()))
        available.update(KNOWN_STANDARD_OBJECT_FIELDS.get(object_name, set()))
        available.update(KNOWN_SCHEMA_OMITTED_OBJECT_FIELDS.get(object_name, set()))
        if not available:
            return []

        sorted_fields = sorted(available)
        close = get_close_matches(field_name, sorted_fields, n=limit, cutoff=0.35)
        suggestions = list(close)
        preferred = ("Id", "Name", "Status", "OwnerId", "CreatedDate")
        for field in preferred:
            if len(suggestions) >= limit:
                break
            if field in available and field not in suggestions:
                suggestions.append(field)
        for field in sorted_fields:
            if len(suggestions) >= limit:
                break
            if field not in suggestions:
                suggestions.append(field)
        return [f"{object_name}.{field}" for field in suggestions]

    def _format_field_suggestions(self, suggestions: Sequence[str]) -> str:
        if not suggestions:
            return ""
        bullets = "\n".join(f"- {field}" for field in suggestions)
        return (
            "\n\nAvailable fields from the benchmark schema that may be relevant include:\n"
            f"{bullets}\n"
            "There may be other valid schema fields not shown here."
        )

    def _balanced_quotes(self, query: str) -> Optional[VerificationResult]:
        for quote in ("'", '"'):
            escaped = False
            in_quote = False
            for char in query:
                if escaped:
                    escaped = False
                    continue
                if char == "\\":
                    escaped = True
                    continue
                if char == quote:
                    in_quote = not in_quote
            if in_quote:
                return self._invalid("UNBALANCED_QUOTES", "The query has unbalanced quotes. Close quoted strings before executing.")
        return None

    def _balanced_parentheses(self, query: str) -> bool:
        depth = 0
        in_quote = None
        escaped = False
        for char in query:
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if in_quote:
                if char == in_quote:
                    in_quote = None
                continue
            if char in {"'", '"'}:
                in_quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth < 0:
                    return False
        return depth == 0

    def _strip_string_literals(self, query: str) -> str:
        output = []
        in_quote = None
        escaped = False
        for char in query:
            if escaped:
                escaped = False
                if not in_quote:
                    output.append(char)
                continue
            if char == "\\":
                escaped = True
                if not in_quote:
                    output.append(char)
                continue
            if in_quote:
                if char == in_quote:
                    in_quote = None
                    output.append(" ")
                continue
            if char in {"'", '"'}:
                in_quote = char
                output.append(" ")
            else:
                output.append(char)
        return "".join(output)

    def _split_top_level(self, text: str, delimiter: str) -> List[str]:
        parts = []
        start = 0
        depth = 0
        in_quote = None
        escaped = False
        for index, char in enumerate(text):
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if in_quote:
                if char == in_quote:
                    in_quote = None
                continue
            if char in {"'", '"'}:
                in_quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth = max(0, depth - 1)
            elif char == delimiter and depth == 0:
                parts.append(text[start:index].strip())
                start = index + 1
        tail = text[start:].strip()
        if tail:
            parts.append(tail)
        return parts

    def _invalid(self, error_code: str, feedback: str) -> VerificationResult:
        return VerificationResult(valid=False, error_code=error_code, feedback=feedback, status="INVALID")

    def _unknown(self, error_code: str, feedback: str, rule: Optional[str] = None) -> VerificationResult:
        return VerificationResult(valid=True, error_code=error_code, feedback=feedback, status="UNKNOWN", rule=rule)
