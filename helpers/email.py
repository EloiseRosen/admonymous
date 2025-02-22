import logging
import os
from django.template import loader
from email.utils import parseaddr
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, From, To, Content

class EmailMessage(object):
    def __init__(self, sender=None, to=None, subject=None):
        self.sender = sender
        self.to = to
        self.subject = subject
        self.html = None
        self.body =  None

    def render_and_send(self, template_name, additional_template_values):
        DEBUG = os.environ.get('SERVER_SOFTWARE', '').startswith('Dev') # TODO
        
        template_values = {
            'full_width': 620,
            'link_style': 'style="text-decoration:none;color:#000099;"',
        }
        template_values.update(additional_template_values)

        if DEBUG:
            template_values['host_url'] = 'http://localhost:8080'
        else:
            template_values['host_url'] = 'https://www.admonymous.co'

        self.html = loader.render_to_string(f'_email/{template_name}.html', template_values)
        self.body = loader.render_to_string(f'_email/{template_name}.txt', template_values)

        # if in dev, just log.  otherwise, actually send.
        if DEBUG:
            logging.info(f"""
HTML Version:

{self.html}

TXT Version:

{self.body}
""")
        else:
            self.send()

    def render(self, template_name, additional_template_values):
        """
        If you only want to render templates, not send yet.
        Returns a dict with 'html' and 'txt'.
        """
        DEBUG = os.environ.get('SERVER_SOFTWARE', '').startswith('Dev')
        template_values = {
            'full_width': 620,
            'link_style': 'style="text-decoration:none;color:#000099;"',
        }
        template_values.update(additional_template_values)
        template_values['host_url'] = 'http://localhost:8080' if DEBUG else 'https://www.admonymous.co'

        html_out = loader.render_to_string(f'_email/{template_name}.html', template_values)
        txt_out = loader.render_to_string(f'_email/{template_name}.txt', template_values)
        return {'html': html_out, 'txt': txt_out}

    def send(self):
        """
        use SendGrid to send email
        """
        sg_api_key = os.environ.get('SENDGRID_API_KEY')
        if not sg_api_key:
            logging.error("SENDGRID_API_KEY not found in environment")
            return

        sg = SendGridAPIClient(sg_api_key)
        from_name, from_email = parseaddr(self.sender or "notify@admonymous.co")
        if not from_email:
            from_email = "notify@admonymous.co"

        to_name, to_email = parseaddr(self.to or "notify@admonymous.co")
        if not to_email:
            to_email = "notify@admonymous.co"

        message = Mail(
            from_email=From(from_email, from_name or None),
            to_emails=[To(to_email, to_name or None)],
            subject=self.subject,
            html_content=self.html,
            plain_text_content=self.body
        )
        try:
            response = sg.send(message)
            logging.info(f"Email sent! SendGrid response code: {response.status_code}")
        except Exception as e:
            logging.exception('error: failed to send email with SendGrid')
