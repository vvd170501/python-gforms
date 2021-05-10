import json
import random
import re
from enum import IntEnum
from bs4 import BeautifulSoup as BS

# based on https://gist.github.com/gcampfield/cb56f05e71c60977ed9917de677f919c


def add_indent(text, indent):
    if not indent:
        return text
    spaces = ' ' * indent
    return ''.join(spaces + line for line in text.splitlines(keepends=True))


class ElementType(IntEnum):
    # File upload is not included
    SHORT = 0
    PARAGRAPH = 1
    RADIO = 2
    DROPDOWN = 3
    CHECKBOXES = 4
    SCALE = 5
    COMMENT = 6
    GRID = 7  # TODO differentiate radio and checkboxes
    PAGE = 8
    DATE = 9  # TODO check format
    TIME = 10  # TODO check format
    IMAGE = 11
    VIDEO = 12

    def is_input_type(self):
        cls = type(self)
        return self < cls.COMMENT or self in [cls.GRID, cls.DATE, cls.TIME]

    def is_choice_type(self):
        cls = type(self)
        return cls.RADIO <= self <= cls.SCALE or self == cls.GRID


class Element:
    class Index:
        NAME = 1
        DESCRIPTION = 2
        TYPE = 3
######
        ID = 0
        VALUE = 4
        OPTIONS = 1
        REQUIRED = 2
######

    def __init__(self, elem):
        self.name = elem[self.Index.NAME]
        self.description = elem[self.Index.DESCRIPTION]  # may be None
        self.type = elem[self.Index.TYPE]

    def to_str(self, indent=0):
        if self.description:
            return f'{self.name} ({self.description})'
        return self.name


class InputElement(Element):
    pass


class Page:
    def __init__(self, elem=None):
        self.elements = []
        if elem is None:
            self.title = None
            self.description = None
        else:
            self.title = elem[Element.Index.NAME]
            self.description = elem[Element.Index.DESCRIPTION]

    def append(self, elem):
        self.elements.append(elem)

    def to_str(self, indent=0):
        if self.description:
            title = f'{self.title} ({self.description})'
        elif self.title:
            title = self.title
        else:
            title = 'First page'
        return '\n'.join([title] + [add_indent(elem.to_str(indent), indent) for elem in self.elements])


class GForm:
    class Index:
        FORM = 1
        DESCRIPTION = 0
        FIELDS = 1
        TITLE = 8
        URL = 14  # top-level, index may change?

    def __init__(self, url):
        self.url = url
        self.fbzx = None
        self.title = None
        self.description = None
        self.pages = None

    def load(self, http, resend=False):
        # does resend actually matter?
        params = {'usp': 'form_confirm'} if resend else None
        page = http.get(self.url, params=params)
        soup = BS(page.text, 'html.parser')
        self.fbzx = self._get_fbzx(soup)
        data = self._raw_form(soup)
        form = data[self.Index.FORM]
        self.title = form[self.Index.TITLE]
        self.description = form[self.Index.DESCRIPTION]
        self.pages = [Page()]

        for elem in form[self.Index.FIELDS]:
            el_type = ElementType(elem[Element.Index.TYPE])
            if el_type == ElementType.PAGE:
                self.pages.append(Page(elem))
                continue
            self.pages[-1].append(self._parse_elem(elem, el_type))

    def to_str(self, indent=0):
        if self.description:
            title = f'{self.title} ({self.description})'
        else:
            title = self.title
        return '\n'.join([title] + [add_indent(page.to_str(indent), indent) for page in self.pages])

    @staticmethod
    def _parse_elem(elem, el_type):
        print('!!', elem)
        if not el_type.is_input_type():
            return Element(elem)
        return InputElement(elem)
        field = {
            'name': elem[NAME],
            'description': elem[DESCRIPTION],
            'type': el_type,
            'id': elem[VALUE][0][ID],
            'required': elem[VALUE][0][REQUIRED],
            'submit_id': 'entry.' + str(elem[VALUE][0][ID]),
        }

        if field['type'].is_choice_type():
            field['options'] = _get_options(elem)
        return None

    @staticmethod
    def _get_fbzx(soup):
        return soup.find('input', {'name': 'fbzx'})['value']

    @staticmethod
    def _raw_form(soup):
        script = soup.find_all('script')[3].string
        pattern = re.compile(r'FB_PUBLIC_LOAD_DATA_ = (\[.+\])\n;', re.S)
        data = json.loads(pattern.search(script).group(1))
        return data



def _get_options(elem):
    options_raw = elem[VALUE][0][OPTIONS]
    return list(map(lambda l: l[0], options_raw))


def submit(http, url, pages, fbzx):
    global history
    sub_url = re.sub(r'(.+)viewform.*', r'\1formResponse', url)

    def submit_page(fields, page_idx, continue_, prev=[]):  #check prev for 1 page!!
        def to_ans_list(x):
            if isinstance(x, list):
                x = x[:]
            else:
                x = [x]
            for i in range(len(x)):
                x[i] = str(x[i])
            return x

        payload = {}
        for field in fields:
            if not field.get('value'):
                if not field['required']:
                    payload[field['submit_id']] = ''
                    continue
                else:
                    raise RuntimeError(f'No value for {field["name"]}')

            if field['type'].is_choice_type() and field['value'] not in field['options']:  # check!!
                payload[field['submit_id']] = '__other_option__'
                payload[field['submit_id'] + '.other_option_response'] = field['value']
            else:
                payload[field['submit_id']] = field['value']

        payload['pageHistory']= ",".join(map(str, range(0, page_idx + 1)))
        payload['fbzx'] = fbzx
        if page_idx == 0:
            prev_fields = None
        else:
            prev_fields = [
                [
                    None,
                    elem['id'],
                    to_ans_list(elem.get('value', '')),
                    0  # ??
                ] for elem in prev
            ]
        payload['draftResponse'] = json.dumps([
           prev_fields,
           None, # ?
           fbzx
        ], ensure_ascii=False)
        
        if continue_:
            payload['continue'] = 1

        #print(payload)
        return http.post(sub_url, data=payload)

    #print(sub_url)
    res = []
    prev = []
    next_page = 0
    for i, page in enumerate(pages):
        if i < next_page:
            continue
        sub_result = submit_page(page, i, i < len(pages) - 1, prev=prev)  # TODO parse pagehistory and draft from response / first page
        res.append(sub_result)
        if sub_result.status_code != 200:
            raise RuntimeError(res)
        soup = BS(sub_result.text, 'html.parser')
        prev += page
        ph = soup.find('input', {'name': 'pageHistory'})
        if ph is None:
            break  # finished?
        next_page = int(ph['value'].rsplit(',', 1)[-1])
    return res


def random_subset(a, nonempty=True):
    res = []
    while True:  # refactor?
        for el in a:
            if random.random() < 0.5:
                res.append(el)
        if res or not nonempty:  # looks awful
            return res


def fill_data(pages, fill_optional=False):
    for i, page in enumerate(pages):
        for field in page:
            if 'fixed_value' in field:
                field['value'] = field['fixed_value']
                continue
            if 'generator' in field:
                field['value'] = field['generator']()
                continue
            if not (field['required'] or fill_optional):
                continue
            if field['type'] in [ElementType.SCALE, ElementType.DROPDOWN]:
                field['value'] = random.choice(field['options'])
                continue
            if field['type'] == ElementType.RADIO:
                # Don't auto-choose "Other"
                opts = [opt for opt in field['options'] if opt]
                field['value'] = random.choice(opts)
                continue
            if field['type'] == ElementType.CHECKBOXES:
                # Don't auto-choose "Other"
                opts = [opt for opt in field['options'] if opt]
                field['value'] = random_subset(opts)
                continue

            print(f'{field["name"]}: {field["type"]}, {field.get("options")}')
            field['value'] = input()
