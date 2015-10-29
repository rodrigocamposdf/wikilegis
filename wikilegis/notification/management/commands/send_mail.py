# -*- coding: utf-8 -*-
from collections import defaultdict
from datetime import datetime
from django.contrib.contenttypes.models import ContentType
from django.contrib.sites.models import Site
from django.core.management.base import BaseCommand
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django_comments.models import Comment
from wikilegis.auth2.models import User
from wikilegis.core.models import Bill, CitizenAmendment, UpDownVote
from wikilegis.notification.models import HistoryNotification


class Command(BaseCommand):
    def handle(self, *args, **options):
        bills = Bill.objects.all()
        current_site = Site.objects.get_current()
        for bill in bills:
            segment_amendments = defaultdict(list)
            amendment_comments = defaultdict(list)
            top_amendments = []
            for segment in bill.segments.all():
                up_votes_segment = UpDownVote.objects.filter(segment=segment, vote='up').count()
                down_votes_segment = UpDownVote.objects.filter(segment=segment, vote='down').count()
                score_segment = up_votes_segment - down_votes_segment
                for amendment in segment.amendments.all():
                    try:
                        last_email = HistoryNotification.objects.get(amendment=amendment)
                        comments = Comment.objects.filter(object_pk=amendment.pk,
                                                          content_type=ContentType.objects.get_for_model(CitizenAmendment),
                                                          submit_date__gte=last_email.hour)
                        if comments:
                            for comment in comments:
                                amendment_comments[amendment].append(comment)
                            last_email.hour = datetime.now()
                            last_email.save()
                    except HistoryNotification.DoesNotExist:
                        segment_amendments[segment].append(amendment)
                        comments = Comment.objects.filter(object_pk=amendment.pk,
                                                          content_type=ContentType.objects.get_for_model(CitizenAmendment))
                        history = HistoryNotification()
                        history.amendment = amendment
                        history.hour = datetime.now()
                        if comments:
                            for comment in comments:
                                amendment_comments[amendment].append(comment)
                                history.hour = datetime.now()
                        history.save()
                    up_votes_amendment = UpDownVote.objects.filter(amendment=amendment, vote='up').count()
                    down_votes_amendment = UpDownVote.objects.filter(amendment=amendment, vote='down').count()
                    score_amendment = up_votes_amendment - down_votes_amendment
                    if score_amendment > score_segment:
                        top_amendments.append(amendment.id)
            if segment_amendments or amendment_comments or top_amendments:
                html = render_to_string('notification/notification_email.html',
                                        {'current_site': current_site, 'bill': bill.title,
                                         'amendments': dict(segment_amendments),
                                         'comments': dict(amendment_comments),
                                         'top_amendments': CitizenAmendment.objects.filter(id__in=top_amendments)})
                superusers = User.objects.filter(is_superuser=True)
                email_list = []
                subject = u'[Wikilegis] Atualizações ao %s' % bill.title
                for superuser in superusers:
                    email_list.append(superuser.email)
                for editor in bill.editors.all():
                    for user in editor.user_set.all():
                        email_list.append(user.email)
                mail = EmailMultiAlternatives(subject, '', '', email_list)
                mail.attach_alternative(html, 'text/html')
                mail.send()