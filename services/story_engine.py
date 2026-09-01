class StoryEngine:

    def __init__(self):
        pass

    def analyse(self, story):

        score = 0
        tags = []

        title = (
            story.get("Proposal", "")
            + " "
            + story.get("Decision", "")
            + " "
            + story.get("Address/Site", "")
        ).lower()

        keywords = {

            "battery": 40,
            "solar": 35,
            "wind": 35,
            "school": 25,
            "housing": 30,
            "houses": 30,
            "retail": 25,
            "industrial": 20,
            "warehouse": 20,
            "supermarket": 35,
            "aldi": 40,
            "lidl": 40,
            "morrisons": 40,
            "tesco": 40,
            "care home": 35,
            "hospital": 35,
            "listed": 30,
            "conservation": 30,
            "demolition": 35,
            "traveller": 50,
            "gypsy": 50,
            "employment": 30,
            "factory": 25

        }

        for word, value in keywords.items():

            if word in title:
                score += value
                tags.append(word)

        if score > 100:
            score = 100

        story["Score"] = score
        story["Tags"] = tags

        return story