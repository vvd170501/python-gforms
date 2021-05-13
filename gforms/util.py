import random


SEP_WIDTH = 50


def page_separator(indent):
    return '=' * SEP_WIDTH


def elem_separator(indent):
    return '—' * (SEP_WIDTH - indent)


def add_indent(text, indent):
    if not indent:
        return text
    spaces = ' ' * indent
    return ''.join(spaces + line for line in text.splitlines(keepends=True))


def random_subset(a, nonempty=True):
    def subset(a):
        res = []
        for el in a:
            if random.random() < 0.5:
                res.append(el)
        return res

    if nonempty:
        if not a:
            raise ValueError('Cannot generate a non-empty subset of an empty set')
        if len(a) == 1:
            return a[:]

    res = subset(a)
    if nonempty:
        while not res:  # P <= 1/16
            res = subset(a)
    return res
