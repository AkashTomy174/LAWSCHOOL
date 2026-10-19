"""Create the WhatsApp template rows (approval status stays 'unknown')."""

from django.core.management.base import BaseCommand

from apps.notifications.whatsapp.templates import SPECS, seed_templates


class Command(BaseCommand):
    help = "Seed NotificationTemplate rows and print the body text to submit to Meta."

    def add_arguments(self, parser):
        parser.add_argument("--show-bodies", action="store_true")

    def handle(self, *args, **options):
        created = seed_templates()
        self.stdout.write(self.style.SUCCESS(f"{created} template(s) created."))
        if options["show_bodies"]:
            for spec in SPECS.values():
                self.stdout.write(f"\n[{spec.meta_category}] {spec.name}\n  {spec.body}")
