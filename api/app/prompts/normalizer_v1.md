A model answered a task but did not return the structured fields the pipeline needs. Recover
them from its prose.

$data_rule

The answer:

$answer

Rules — this is extraction, not interpretation:

- Every `key_claims` entry must be a claim the text actually makes, in wording taken from the
  text. Do not summarise across claims, do not sharpen a hedge into an assertion, and do not
  add a claim the author would have made but did not.
- `assumptions` must be things the text itself declares or plainly relies on. Do not infer
  what the author probably assumed.
- `expected_consensus` — only if the text says something about what other models or the
  common view would conclude. Otherwise return null. Null is correct and expected here; a
  fabricated prediction would corrupt the confidence level of the final answer.
