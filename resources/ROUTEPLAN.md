## Flexible implementation plan

1. **Define task families**

   * Start with your selected categories.
   * Map each to one scaffold plus a general fallback.

2. **Create scaffold modules**

   ```python
   TASK_SCAFFOLDS = {
       "quote_approval": QUOTE_APPROVAL_SCAFFOLD,
       "lead_qualification": LEAD_QUALIFICATION_SCAFFOLD,
       "case_routing": CASE_ROUTING_SCAFFOLD,
       "conversion_rate_comprehension": CONVERSION_SCAFFOLD,
       "confidentiality": PRIVACY_SCAFFOLD,
       "general": GENERAL_SCAFFOLD,
   }
   ```

3. **Implement a realistic router (instead of oracle router)**

   * Use only the visible user request and conversation history.
   * Begin with deterministic keyword/rule matching.
   * Return:

   ```python
   RoutingResult(
       task_family="quote_approval",
       confidence=0.92,
       evidence=["quote", "company policy"],
   )
   ```
   * Collect data on how aligned our system is on previous benchmark data (how well we're able to deterministically identify the task at hand)

5. **Add uncertainty handling**

   * Use the general scaffold when confidence is low.
   * Optionally reroute after later user turns provide more information.

6. **Inject the scaffold**

   * Add it once to the system prompt after routing.
   * Keep it procedural and task-independent; do not include instance answers or hidden benchmark data.
   * None yet, but will develop after this plan

7. **Log routing behavior**

   * Predicted family
   * Confidence
   * Matched rules
   * Oracle task label
   * Whether the route changed
   * Scaffold used

8. **Evaluate separately**

   * Task success
   * Routing accuracy
   * Success conditional on correct routing
   * General-fallback performance
   * Model calls, environment calls, and verifier retries

Start with oracle routing to validate the scaffolds themselves, then replace it with visible-input routing so routing errors do not obscure whether the specialized procedures are useful.
