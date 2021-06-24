# GForms

A python wrapper for public Google Forms.

**This package does not implement form editing / sharing / other actions with user-owned forms**

## Installation

```shell
python3 -m pip install gforms
```

## Features
- Form parsing
  - All form settings are parsed
  - Multi-page forms are supported
  - Elements with input validation are supported
- Form filling
  - Fill the entire form using a single callback function (see [example](#example))
  - Fill individual elements
  - Validate the form before submission
- Form submission
  - Faster submission for multi-page forms (history emulation)

## Limitations
 - Forms with required sign-in cannot be submitted
 - Forms with file upload cannot be parsed (sign-in is required for loading the form)
 - A CAPTCHA needs to be solved in order to send an e-mail with a response copy (when this option is enabled). CAPTCHA handling should be implemented separately
 - Form style is not parsed


## Example

See [example.py](https://github.com/vvd170501/python-gforms/blob/master/example.py) for more details.

```python3
from gforms import Form
from gforms.elements import Short, Value

def callback(element, page_index, element_index):
    # fill an element based on its position
    if page_index == 0 and element_index == 1:
        return 'Yes'
    # fill an element based on its type and name
    if isinstance(element, Short) and element.name == 'Your opinion:':
        return input(element.name)
    # fill choice elements with random values, skip optional elements if fill_optional is not used
    return Value.DEFAULT

url = 'https://docs.google.com/forms/d/e/.../viewform'

form = Form()

form.load(url)
print(form.to_str(indent=2))  # a text representation, may be useful for CLI applications

form.fill(callback)
form.submit()

# Faster submission for multi-page forms (use only one POST request)
# (in theory, you may get banned, but now the actual number of requests isn't checked)
form.submit(emulate_history=True)
```
