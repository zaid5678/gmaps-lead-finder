"""
Email templates for cold outreach to local businesses without websites.

Three-stage sequence:
  1. initial    — first contact, offers a free mock-up
  2. follow_up  — gentle reminder after 3 days
  3. final      — last attempt after 7 days, low pressure
"""

from dataclasses import dataclass


@dataclass
class EmailTemplate:
    subject: str
    body: str


def initial_outreach(business_name: str, city: str, industry: str) -> EmailTemplate:
    subject = f"Quick idea for {business_name} — more local enquiries online"
    body = f"""Hi {business_name},

Hope you're well.

I came across your {industry} on Google Maps and noticed you don't currently have a website. I wanted to reach out because I think there's a real opportunity here.

Most people in {city} searching for a {industry} will compare a few options online before deciding. Without a website, they often move on to a competitor who makes it easy to see services and get in touch — even if your Google reviews are excellent.

A simple, professional website could help you:
• Appear in more local searches
• Let customers find and contact you easily, any time
• Turn more online searches into real bookings

I specialise in building clean, affordable websites for local businesses like yours — designed to generate enquiries, not just look nice. Usually takes less than a week to go live.

I'd be happy to put together a free mock-up for {business_name} so you can see exactly how it would look before making any decision.

Worth a look?

Best,
Zaid
zfkhan321@gmail.com"""
    return EmailTemplate(subject=subject, body=body)


def follow_up_3_days(business_name: str, city: str, industry: str) -> EmailTemplate:
    subject = f"Following up — website for {business_name}"
    body = f"""Hi {business_name},

Just a quick follow-up to my message from a few days ago — I know you're busy.

I reached out because I think a simple website could make a real difference for your {industry} in {city}. Your Google reviews speak for themselves — a website would give people a proper place to land when they search for what you offer.

I'm still happy to put together a free, no-obligation mock-up so you can see what it would look like before deciding anything.

If you're interested, just reply with a quick "yes" and I'll get it over to you.

Best,
Zaid"""
    return EmailTemplate(subject=subject, body=body)


def final_follow_up(business_name: str, city: str, industry: str) -> EmailTemplate:
    subject = f"Last message — {business_name} website"
    body = f"""Hi {business_name},

I'll keep this brief — this is my last message.

I reached out because I genuinely think {business_name} could pick up more customers with a website, and I've helped similar {industry} businesses in {city} do exactly that.

If the timing isn't right, no problem at all — best of luck with everything.

But if you'd ever like to see a free mock-up, just drop me a reply whenever. Happy to help.

All the best,
Zaid
zfkhan321@gmail.com"""
    return EmailTemplate(subject=subject, body=body)


TEMPLATE_FUNCTIONS = {
    "initial": initial_outreach,
    "follow_up": follow_up_3_days,
    "final": final_follow_up,
}


def get_template(name: str, business_name: str, city: str, industry: str) -> EmailTemplate:
    fn = TEMPLATE_FUNCTIONS.get(name)
    if fn is None:
        raise ValueError(f"Unknown template '{name}'. Choose from: {list(TEMPLATE_FUNCTIONS)}")
    return fn(business_name, city, industry)
