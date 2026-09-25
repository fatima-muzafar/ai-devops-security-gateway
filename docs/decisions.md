rollback_deployment sensitivity = HIGH (not "Medium-High" per Section 12's ambiguous wording).
Rationale: Section 11's decision table treats production + irreversible/high-impact
actions as the top tier; rollback mutates current_version same as deploy_service.