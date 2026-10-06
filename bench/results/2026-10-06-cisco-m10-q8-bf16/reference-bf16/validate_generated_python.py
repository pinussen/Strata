"""Validate this specific manually reviewed response, not arbitrary model code."""
import ast
import json
from pathlib import Path
import random

root = Path(__file__).resolve().parent
response = (root / 'generated-python.txt').read_text()
assert response.startswith('```python\n') and response.endswith('\n```')
source = response[len('```python\n'):-len('\n```')]
(root / 'reviewed-merge-sorted.py').write_text(source + '\n')
tree = ast.parse(source)
assert len(tree.body) == 1 and isinstance(tree.body[0], ast.FunctionDef)
assert tree.body[0].name == 'merge_sorted'
# The saved function was reviewed: list indexing, append, integer increments and len only.
namespace = {'__builtins__': {'len': len}}
exec(compile(tree, 'reviewed-merge-sorted.py', 'exec'), namespace)
merge = namespace['merge_sorted']
cases = [([], []), ([], [1, 2]), ([1, 2], []), ([1, 1], [1, 1]),
         ([-5, -1, 0], [-4, 0, 3]), ([0], list(range(50))),
         ([-1.5, 0.0, 3.5], [-2.0, 0.0, 4.0])]
rng = random.Random(1010)
for _ in range(100):
    cases.append((sorted(rng.randint(-50, 50) for _ in range(rng.randrange(65))),
                  sorted(rng.randint(-50, 50) for _ in range(rng.randrange(65)))))
for a, b in cases:
    before = (a.copy(), b.copy())
    result = merge(a, b)
    assert result == sorted(a + b), (a, b, result)
    assert (a, b) == before
    assert result is not a and result is not b
report = {'state': 'passed', 'cases': len(cases), 'random_seed': 1010,
          'checks': ['sorted merge', 'duplicates retained', 'inputs unchanged', 'new result list'],
          'review': 'Manually reviewed before execution; Markdown fence removed.',
          'format_note': 'Response used Markdown despite requesting only Python code.'}
(root / 'python-validation.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
