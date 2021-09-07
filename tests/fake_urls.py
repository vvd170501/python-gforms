from abc import abstractmethod, ABC


class Placeholder(str, ABC):
    marker: str  # should be unique for each class

    @property
    @abstractmethod
    def marker(self):
        raise NotImplementedError()

    def __new__(cls, value: str):
        return super().__new__(cls, cls.marker + value + cls.marker)


class FormId(Placeholder):
    marker = '@@'


class ResponseId(Placeholder):
    marker = '$$'


placeholders = [FormId, ResponseId]


class UrlMeta(type):
    def __getattr__(cls, key):
        if key not in cls.__annotations__:
            raise AttributeError()
        return f'https://docs.google.com/forms/d/e/{FormId(key)}/viewform'


class FormUrl(metaclass=UrlMeta):
    empty: str
    pages: str
    elements: str
    non_input: str
    text: str
    required: str
    radio: str
    dropdown: str
    checkboxes: str
    scale: str
    grid: str
    date: str
    time: str

    file_upload: str

    text_validation: str
    grid_validation: str
    checkbox_validation: str

    shuffle_options: str

    settings_email: str
    settings_email_opt_in: str
    settings_email_always: str
    settings_submit_once: str
    settings_edit: str
    settings_stats: str
    settings_pbar: str
    settings_shuffle: str
    settings_no_resubmit_link: str
    settings_confirmation_msg: str
    settings_disable_autosave: str
    settings_quiz: str
    settings_quiz_alt: str

    prefilled = f'https://docs.google.com/forms/d/e/{FormId("prefilled")}/viewform?usp=pp_url&entry.1787303382=text_value'
    edit = f'https://docs.google.com/forms/d/e/{FormId("edit")}/viewform?edit2={ResponseId("response1")}'

    form_validation: str
    fill: str


_yt_link = 'dQw4w9WgXcQ'
yt_url = f'https://youtu.be/{_yt_link}'
