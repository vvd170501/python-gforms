import pytest

from gforms.form import Settings

from .conftest import FormParseTest


class SettingsTest(FormParseTest):
    @pytest.fixture(autouse=True)
    def settings(self):
        self.settings = Settings()

    @staticmethod
    def check(form, settings):
        assert form.settings.__dict__ == settings.__dict__

    def test(self, form):
        self.modify_settings(self.settings)
        self.check(form, self.settings)

    def modify_settings(self, settings):
        pass


class TestDefault(SettingsTest):
    form_type = 'empty'


class TestEmail(SettingsTest):
    form_type = 'settings_email'

    def modify_settings(self, settings):
        settings.collect_emails = Settings.CollectEmails.USER_INPUT
        settings.send_receipt = Settings.SendReceipt.NEVER


class TestEmailOptIn(SettingsTest):
    form_type = 'settings_email_opt_in'

    def modify_settings(self, settings):
        settings.collect_emails = Settings.CollectEmails.USER_INPUT
        settings.send_receipt = Settings.SendReceipt.OPT_IN


class TestEmailAlways(SettingsTest):
    form_type = 'settings_email_always'

    def modify_settings(self, settings):
        settings.collect_emails = Settings.CollectEmails.USER_INPUT
        settings.send_receipt = Settings.SendReceipt.ALWAYS


class TestSubmitOnce(SettingsTest):
    form_type = 'settings_submit_once'

    def modify_settings(self, settings):
        settings.submit_once = True

    def test(self, form):
        super().test(form)
        assert form.requires_signin
        assert not form.settings.show_resubmit_link


class TestEdit(SettingsTest):
    form_type = 'settings_edit'

    def modify_settings(self, settings):
        settings.edit_responses = True


class TestSummary(SettingsTest):
    form_type = 'settings_stats'

    def modify_settings(self, settings):
        settings.show_summary = True


class TestPbar(SettingsTest):
    form_type = 'settings_pbar'

    def modify_settings(self, settings):
        settings.show_progressbar = True


class TestShuffle(SettingsTest):
    form_type = 'settings_shuffle'

    def modify_settings(self, settings):
        settings.shuffle_questions = True


class TestNoResub(SettingsTest):
    form_type = 'settings_no_resubmit_link'

    def modify_settings(self, settings):
        settings.show_resubmit_link = False


class TestConfirmationMsg(SettingsTest):
    form_type = 'settings_confirmation_msg'

    def modify_settings(self, settings):
        settings.confirmation_msg = 'custom_text'


class TestDisableAutosave(SettingsTest):
    form_type = 'settings_disable_autosave'

    def modify_settings(self, settings):
        settings.disable_autosave = True


class TestQuiz(SettingsTest):
    form_type = 'settings_quiz'

    def modify_settings(self, settings):
        settings.is_quiz = True


class TestQuizAlt(SettingsTest):
    form_type = 'settings_quiz_alt'

    def modify_settings(self, settings):
        settings.is_quiz = True
        settings.immediate_grades = False
        # collect_emails is automatically enabled when immediate_grades are disabled
        # It may be disabled manually
        settings.collect_emails = Settings.CollectEmails.USER_INPUT
        settings.send_receipt = Settings.SendReceipt.NEVER
        settings.show_missed = False
        settings.show_correct_answers = False
        settings.show_points = False
