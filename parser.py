import json
from urllib.parse import urlparse
import os

def get_last_path_segment(url: str) -> str:
    """
        Parses a URL and returns the last segment of the path.
        Handles cases with trailing slashes.
    """
    parsed_url = urlparse(url)
    path = parsed_url.path

    # Use os.path.basename to get the last path component
    # This correctly handles both '/path/to/file' and '/path/to/directory/'
    last_segment = os.path.basename(os.path.normpath(path))
    return last_segment



if __name__ == "__main__":
    document = ""
    with open("schools.json") as f:
        entities = json.load(f)
        for entity in entities:
            school = get_last_path_segment(entity["url"])
            if school:
                document += f"# {school}\n"
            for key, name in zip(["presentation_content", "concours_content", "admission_content", "threshold_content"], ["Presentation", "Concours", "Inscription", "Admission"]):
                if entity[key]:
                    document += f"## {name}\n"
                    document += f"{entity[key]}\n"
    with open("nation.md", "w") as f:
        f.write(document)

    document = ""
    with open("study_Abroad.json") as f:
        entities = json.load(f)
        for entity in entities:
            if len(entity) > 2:
                description = entity[0]["description"]
                contents = "\n".join([item for sublist in entity[1:] for item in sublist])
                # contents = sum(entity[1:])
                document += f"# {description}\n"
                document += f"{contents}\n"
                # for content in contents:
                #     document += f"## {content}\n"
    with open("abroad.md", "w") as f:
        f.write(document)

