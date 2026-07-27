# Lead Qualification Clipboard Plan

## Goal

Create a deterministic, nonblocking clipboard that organizes retrieved evidence around the four BANT factors:

* Budget
* Authority
* Need
* Timeline

The LLM reads the clipboard but does not edit it directly.

## State

Track:

```python
@dataclass
class LeadClipboard:
    lead_id: str
    lead_retrieved: bool = False
    qualification_guides: dict = field(default_factory=dict)
    inspected_guide_ids: set[str] = field(default_factory=set)

    transcripts_retrieved: bool = False
    transcript_ids: list[str] = field(default_factory=list)

    bant_evidence: dict = field(
        default_factory=lambda: {
            "Budget": [],
            "Authority": [],
            "Need": [],
            "Timeline": [],
        }
    )

    failed_queries: list[str] = field(default_factory=list)
```

## Update Logic

After each successful Salesforce query:

* store the lead record;
* record qualification-guide candidates;
* mark detailed guides as inspected;
* store retrieved call transcripts;
* assign transcript excerpts to BANT categories using deterministic keywords;
* record failed queries separately.

Keyword matching only marks an excerpt as relevant. It must not decide whether a BANT factor passes or fails.

## Rendered Clipboard

Inject a compact temporary message before each model call:

```text
# Lead qualification evidence

Guide inspected: yes
Transcripts retrieved: 2

Budget:
- “We have allocated $80,000.”

Authority:
- “The CFO must give final approval.”

Need:
- “Our current system cannot support reporting.”

Timeline:
- “We need deployment before Q4.”

Compare each factor against the qualification guide.
Return only failed BANT factors.
```

## Guidance

Display a suggested next goal:

* retrieve the guide;
* retrieve recent transcripts;
* find evidence for BANT factors with no excerpts;
* evaluate all four factors.

Treat this as guidance, not hard flow control.

## Final-Answer Check

Allow only:

```text
Budget
Authority
Need
Timeline
```

a comma-separated subset, or `None`.

Reject explanations, repeated factors, and unsupported output formats.

## Initial Evaluation

Compare:

1. lead scaffold only;
2. scaffold plus BANT clipboard;
3. scaffold plus clipboard and final-format check.

Measure task success, missing-factor errors, model calls, environment steps, and formatting failures.
