import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send_report(html_body: str, subject: str, to_email: str, gmail_user: str, gmail_app_password: str):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = gmail_user
    msg['To'] = to_email

    part = MIMEText(html_body, 'html')
    msg.attach(part)

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(gmail_user, gmail_app_password)
        server.sendmail(gmail_user, to_email, msg.as_string())

    print(f"Email sent to {to_email}")
