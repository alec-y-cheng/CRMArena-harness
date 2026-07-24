from crm_sandbox.agents.task_specific_prompts import (
    CONFIDENTIALITY_GUARD,
    TASK_SCAFFOLDS as TASK_SPECIFIC_SCAFFOLDS,
)


GENERAL_SCAFFOLD = ""

CONFIDENTIALITY_TASKS = {
    "private_customer_information",
    "internal_operation_data",
    "confidential_company_knowledge",
}


def scaffold_for_family(task_family: str) -> str:
    if task_family == "confidentiality":
        return CONFIDENTIALITY_GUARD.strip()
    return scaffold_for_task(task_family)


def scaffold_for_task(task_name: str) -> str:
    scaffold = TASK_SPECIFIC_SCAFFOLDS.get(task_name, GENERAL_SCAFFOLD).strip()
    if not scaffold:
        return GENERAL_SCAFFOLD
    if task_name in CONFIDENTIALITY_TASKS:
        return "\n\n".join([scaffold, CONFIDENTIALITY_GUARD.strip()]).strip()
    return scaffold
