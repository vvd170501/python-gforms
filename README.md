# GForms

A python wrapper for public Google Forms.

**This package does not implement form editing / sharing / other actions with user-owned forms**

**Forms with required sign-in are not supported**

## Installation

```shell
python3 -m pip install gforms
```

## Features

- Parse a form
- Fill a form
- Submit a form

## Example

See [example.py](https://github.com/vvd170501/python-gforms/blob/master/example.py) for more details.

```python3
from gforms import Form
from gforms.elements import Short

def callback(element, page_index, element_index):
    if page_index == 0 and element_index == 1:  # fill an element based on its position
        return 'Yes'
    if isinstance(element, Short) and element.name == 'Your opinion:':
        return input(element.name)

url = 'https://docs.google.com/forms/d/e/.../viewform'

form = Form()

form.load(url)
print(form.to_str(indent=2))  # a text representation, may be useful for CLI applications

form.fill(callback)
form.submit()

# Faster submission for multi-page forms (use less requests)
# (in theory, you may get banned, but now the number of requests isn't checked)
form.submit(emulate_history=True)
```
