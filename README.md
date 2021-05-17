# GForms

A python wrapper for public Google Forms.

**This package does not implement form editing / sharing / other actions with user-owned forms**

**Forms with required sign-in are not supported**

## Features

- Parse a form
- Fill a form
- Submit a form

## Example

```python3
import requests
from gforms import Form
from gforms.elements import Short

def callback(element, page_index, element_index):
    if page_index == 0 and element_index == 1:  # fill an element based on its position
        return 'Yes'
    if isinstance(element, Short) and element,name == 'Your opinion:':
        return input(element.name)

url = 'https://docs.google.com/forms/d/e/.../viewform'
form = Form(url)

form.load(requests)
print(form.to_str(indent=2))  # a text representation, may be useful for CLI applications

form.fill(callback)
form.submit(requests)
```
