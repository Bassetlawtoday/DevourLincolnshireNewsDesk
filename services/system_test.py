from services.planning_scraper import PlanningScraper


def run_system_test():

    scraper = PlanningScraper()

    print()

    print("NEWSDESK SYSTEM TEST")

    print("------------------------")

    if scraper.test_connection():

        print("Planning Portal ........ OK")

    else:

        print("Planning Portal ........ FAILED")

    print()

    print("System Ready.")