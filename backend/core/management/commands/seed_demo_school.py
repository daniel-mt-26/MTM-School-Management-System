from datetime import date

from django.core.management.base import BaseCommand

from core.demo_seed import DEMO_NAME, seed_demo


class Command(BaseCommand):
    help = "Populate an existing is_demo school; --yes explicitly confirms synthetic data writes."

    def add_arguments(self, parser):
        parser.add_argument('--school', default=DEMO_NAME)
        parser.add_argument('--yes', action='store_true')
        parser.add_argument('--reset-first', action='store_true')
        parser.add_argument('--as-of', type=date.fromisoformat, help='Pin the demo calendar (YYYY-MM-DD); persisted across reruns.')
        parser.add_argument('--password', help='Optional demo admin password; prefer MTM_DEMO_ADMIN_PASSWORD environment variable.')
        parser.add_argument('--parent-password', help='Optional demo parent password; prefer MTM_DEMO_PARENT_PASSWORD.')

    def handle(self, *args, **options):
        seeder = seed_demo(options['school'], confirmed=options['yes'], reset=options['reset_first'], as_of=options['as_of'],
                           passwords={'school_admin': options.get('password'), 'parent': options.get('parent_password')})
        # All write operations have completed atomically before credentials are printed.
        counts = seeder.counts
        self.stdout.write(self.style.SUCCESS(f'Demo ready: {seeder.school.name}; calendar {seeder.day}'))
        labels = [('academicyear', 'Academic Years'), ('term', 'Terms'), ('schoolclass', 'Classes'), ('student', 'Students'),
                  ('parent', 'Parents'), ('teacher', 'Teachers'), ('teacherassignment', 'Teacher Assignments'),
                  ('attendancerecord', 'Attendance Records'), ('homework', 'Homework'), ('staffannouncement', 'Announcements'),
                  ('academicresult', 'Results'), ('published_results', 'Published Results'), ('recurringfeetemplate', 'Fee Structures'),
                  ('studentfeeassignment', 'Charges'), ('payment', 'Payments'), ('receipt', 'Receipts'), ('studentinvoice', 'Invoices'),
                  ('expense', 'Expenses'), ('cashbook_records', 'Cashbook Records'), ('inventoryitem', 'Inventory Items'), ('auditlog', 'Audit Events')]
        for key, label in labels:
            self.stdout.write(f'{label}: {counts.get(key, 0)}')
        self.stdout.write('Demo administrator: ' + seeder.actor.username)
        for teacher in seeder.teachers:
            self.stdout.write('Demo teacher: ' + teacher.user.username)
        self.stdout.write('Walkthrough parent: ' + seeder.parents[0].user.username)
        for username, generated in seeder.credentials:
            if generated:
                self.stdout.write(f'Generated temporary demo password (shown once) {username}: {generated}')
        self.stdout.write('Existing credentials are preserved; first sign-in requires password change for newly created accounts.')
