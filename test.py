import resend
resend.api_key = "re_UkDuEtsu_FdkzQbjvmhNqM8tFXJw4s2iw"

from resend import Emails

response = Emails.send({
    "from": "FlockTogether <admin@flocktogether.xyz>",
    "to": ["arun.etech2011@gmail.com"],
    "subject": "Test Email",
    "html": "<p>Hello from Flock</p>"
})

print("===== RESEND RESPONSE =====")
print(response)
