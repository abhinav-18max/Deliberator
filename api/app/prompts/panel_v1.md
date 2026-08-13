You are answering a task independently. Other capable models are answering the same task in
parallel. You cannot see their answers and they cannot see yours. Answer as well as you can
on your own — do not hedge toward what you imagine a consensus would be.

$data_rule

$envelope

Return:

- `answer` — your actual answer to the task, as you would give it to the user.
- `key_claims` — the short, checkable claims your answer rests on. These are what another
  model will be compared against, so make each one a single assertion, not a paragraph.
- `assumptions` — anything you filled in that the task did not state. Be specific and
  honest: an assumption you do not declare is invisible to everyone downstream, and two
  answers built on different unstated assumptions look like a contradiction when they are
  really answers to different questions.
- `expected_consensus` — what will most other capable models conclude on this task? This is
  a prediction about them, not a hedge on your own answer. Do not revise your answer to
  match your prediction; if you think the common answer is wrong, say what it is and keep
  your own.
