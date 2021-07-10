"""A command-line tool for publishing lessons and chapters to the web.

The tool uses our course builds to generate a web page for each lesson, and
place each lesson in the right chapter.
"""
import re
import json
import dotenv
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence, Set, Generator

import requests
from datargs import arg, parse

dotenv.load_dotenv()

YOUR_MAVENSEED_URL: str = os.environ.get("MAVENSEED_URL", "")
YOUR_EMAIL: str = os.environ.get("MAVENSEED_EMAIL", "")
YOUR_PASSWORD: str = os.environ.get("MAVENSEED_PASSWORD", "")

API_SLUG_LOGIN: str = "/api/login"
API_SLUG_COURSES: str = "/api/v1/courses"
API_SLUG_CHAPTERS: str = "/api/v1/chapters"
API_SLUG_COURSE_CHAPTERS: str = "/api/v1/course_chapters"
API_SLUG_LESSONS: str = "/api/v1/lessons"

ERROR_NO_VALID_LESSON_FILES: int = 1
ERROR_COURSE_NOT_FOUND: int = 2
ERROR_CACHE_FILE_EMPTY: int = 3

CACHE_FILE: Path = Path(".cache") / "courses.json"


@dataclass
class Args:
    """Command-line arguments."""

    course: str = arg(
        positional=True,
        help="The name or URL slug of the course to upload the lessons to.",
    )
    lesson_files: Sequence[Path] = arg(
        positional=True,
        help="A sequence of paths to html files to upload to Mavenseed.",
    )
    overwrite: bool = arg(
        default=True,
        help="If set, overwrite existing lessons in the course. Otherwise, skip existing lessons.",
        aliases=["-o"],
    )
    mavenseed_url: str = arg(
        default=YOUR_MAVENSEED_URL,
        help="""the url of your mavenseed website.
        if you omit this option, the program tries to read it from the environment variable MAVENSEED_URL.
        """,
        aliases=["-u"],
    )
    email: str = arg(
        default=YOUR_EMAIL,
        help="""Your email to log into your Mavenseed's admin account.
        if you omit this option, the program tries to read it from the environment variable MAVENSEED_EMAIL.
        """,
        aliases=["-e"],
    )
    password: str = arg(
        default=YOUR_PASSWORD,
        help="""Your password to log into your Mavenseed's admin account.
        if you omit this option, the program tries to read it from the environment variable MAVENSEED_PASSWORD.
        """,
        aliases=["-p"],
    )
    list_courses: bool = arg(
        default=False, help="List all courses on the Mavenseed website and their ID."
    )


@dataclass
class Course:
    """Metadata for a course returned by the Mavenseed API."""

    id: int
    title: str
    slug: str
    status: str
    created_at: str
    updated_at: str
    scheduled_at: str
    published_at: str
    excerpt: str
    free: bool
    questions_enabled: bool
    signin_required: bool
    view_count: int
    metadata: dict
    banner_data: object

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "slug": self.slug,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "scheduled_at": self.scheduled_at,
            "published_at": self.published_at,
            "excerpt": self.excerpt,
            "free": self.free,
            "questions_enabled": self.questions_enabled,
            "signin_required": self.signin_required,
            "view_count": self.view_count,
            "metadata": self.metadata,
            "banner_data": self.banner_data,
        }


@dataclass
class Chapter:
    """Metadata for a chapter returned by the Mavenseed API."""

    id: int
    course_id: int
    title: str
    content: str
    created_at: str
    updated_at: str
    ordinal: int

    def to_dict(self):
        return {
            "id": self.id,
            "course_id": self.course_id,
            "title": self.title,
            "content": self.content,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "ordinal": self.ordinal,
        }


@dataclass
class NewChapter:
    """Metadata for a new chapter to create on Mavenseed."""

    title: str
    
    def get_slug(self):
        return re.sub("[^a-z0-9]+", "-", self.title.lower())


@dataclass
class NewLesson:
    """Metadata for a new lesson to upload to Mavenseed."""

    slug: str
    filepath: Path

    def get_file_content(self) -> str:
        """Return the content of the file to upload."""
        with open(self.filepath, "r") as f:
            return f.read()

    def get_title(self, content: str) -> str:
        """Return the title of the lesson from the content of the file to upload."""
        title = re.search(r"<title>(.*?)</title>", content)
        if title:
            return title.group(1)
        else:
            return self.slug.replace("-", " ").title()


@dataclass
class Lesson:
    """Metadata for a lesson returned by the Mavenseed API."""

    id: int
    lessonable_type: str
    lessonable_id: int
    title: str
    slug: str
    content: str
    status: str
    created_at: str
    updated_at: str
    ordinal: int
    exercise_votes_threshold: int
    exercise_type: int
    free: bool
    media_type: str
    signin_required: bool
    metadata: dict
    embed_data: object

    def to_dict(self):
        """Convert the lesson to a dictionary."""
        return {
            "id": self.id,
            "lessonable_type": self.lessonable_type,
            "lessonable_id": self.lessonable_id,
            "title": self.title,
            "slug": self.slug,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "ordinal": self.ordinal,
            "exercise_votes_threshold": self.exercise_votes_threshold,
            "exercise_type": self.exercise_type,
            "free": self.free,
            "media_type": self.media_type,
            "signin_required": self.signin_required,
            "metadata": self.metadata,
            "embed_data": self.embed_data,
        }


def validate_lesson_files(files: Sequence[Path]) -> List[Path]:
    """Validates the files to be uploaded to Mavenseed.

    Returns:
        A list of paths to files that should be uploaded.
    """

    def is_valid_file(filepath: Path) -> bool:
        """Returns true if the file is a valid lesson file.

        A valid lesson file is an html file that contains a valid lesson header.
        """
        is_valid: bool = filepath.exists() and filepath.suffix.lower() == ".html"
        with filepath.open() as f:
            return is_valid and bool(re.search(r"<h1>.*</h1>", f.read()))

    return [filepath for filepath in files if is_valid_file(filepath)]


def upload_lesson(
    token: str, course_id: str, lesson_file: Path, overwrite: bool = True
) -> None:
    """Uploads a lesson to Mavenseed using the requests module.

    Args:
        token: your Mavenseed API token.
        course_id: The ID of the course to upload the lesson to.
        lesson_file: The path to the lesson file to upload.
        overwrite: If set, overwrite existing lessons in the course. Otherwise, skip existing lessons.
    """
    pass


def get_auth_token(api_url: str, email: str, password: str) -> str:
    """Logs into the Mavenseed API using your email, password,and API token.

    Args:
        api_url: The URL of the Mavenseed API.
        auth_token: A string containing the API token.
    Returns:
        The authorization token.
    """
    response = requests.post(
        api_url + API_SLUG_LOGIN, data={"email": email, "password": password}
    )
    auth_token = response.json()["auth_token"]
    return auth_token





def get_all_courses(api_url: str, auth_token: str) -> List[Course]:
    """Gets all course IDs from the Mavenseed API.

    Args:
        api_url: The URL of the Mavenseed API.
    Returns:
        A set of course IDs.
    """
    response = requests.get(
        api_url + API_SLUG_COURSES, headers={"Authorization": "Bearer " + auth_token}
    )

    courses: List[Course] = [Course(**course) for course in response.json()]
    return courses


def get_all_chapters_in_course(
    api_url: str, auth_token: str, course_id: int
) -> List[Chapter]:
    """Gets all chapters from the Mavenseed API.

    Args:
        api_url: The URL of the Mavenseed API.
        auth_token: A string containing the API token.
        course_id: The ID of the course to get the chapters from.
    Returns:
        A set of chapters.
    """
    print(f"Getting chapters for course {course_id}.", end="\r")
    response = requests.get(
        f"{api_url}/{API_SLUG_COURSE_CHAPTERS}/{course_id}",
        headers={"Authorization": "Bearer " + auth_token},
    )
    chapters: List[Chapter] = [Chapter(**data) for data in response.json()]
    return chapters


def cache_all_courses(url: str, auth_token: str) -> None:
    """Downloads serializes all courses,chapters, and lessons through the Mavenseed API.
    Returns the data as a dictionary.
    Takes some time to execute, depending on the number of lessons and courses."""

    output = dict()

    def get_all_lessons(api_url: str, auth_token: str) -> Generator:
        """Generator. Gets all lessons from the Mavenseed API.

        Args:
            api_url: The URL of the Mavenseed API.
            auth_token: A string containing the API token.
            course_id: The ID of the course to get the lessons from.
        Returns:
            A set of lessons.
        """
        page: int = 0
        while True:
            print(f"Getting lessons {page * 20} to {(page + 1) * 20}", end="\r")
            response = requests.get(
                f"{api_url}/{API_SLUG_LESSONS}",
                headers={"Authorization": "Bearer " + auth_token},
                params={"page": page},
            )
            lessons: List[Lesson] = [Lesson(**data) for data in response.json()]
            page += 1
            if not lessons:
                break
            yield lessons

    print("Downloading all lessons, chapters, and course data. This may take a while.")
    lessons_lists: List[List[Lesson]] = list(get_all_lessons(url, auth_token))
    lessons: List[Lesson] = [
        lesson for lesson_list in lessons_lists for lesson in lesson_list
    ]

    courses: List[Course] = get_all_courses(url, auth_token)
    for course in courses:
        output[course.title] = []
        chapters: List[Chapter] = get_all_chapters_in_course(url, auth_token, course.id)
        for chapter in chapters:
            lessons_in_chapter_as_dict = [
                lesson.to_dict()
                for lesson in lessons
                if lesson.lessonable_id == chapter.id
            ]
            chapter_as_dict = chapter.to_dict()
            chapter_as_dict["lessons"] = lessons_in_chapter_as_dict
            output[course.title].append(chapter_as_dict)

    if not CACHE_FILE.parent.exists():
        print("Creating .cache/ directory.")
        CACHE_FILE.parent.mkdir()
    print(f"Writing the data of {len(output)} courses to {CACHE_FILE.as_posix()}.")
    json.dump(output, open(CACHE_FILE, "w"), indent=2)


def main():
    args: Args = parse(Args)

    if not args.mavenseed_url:
        raise ValueError(
            """You must provide a Mavenseed URL via the --mavenseed-url command line
            option or set the MAVENSEED_URL environment variable."""
        )

    valid_files: List[Path] = validate_lesson_files(args.lesson_files)
    if len(valid_files) != len(args.lesson_files):
        invalid_files: Set[Path] = {
            filepath for filepath in args.lesson_files if filepath not in valid_files
        }
        for filepath in invalid_files:
            print(f"{filepath} is not a valid lesson file. It won't be uploaded.")
    if len(valid_files) == 0:
        print("No valid lesson files found to upload in the provided list. Exiting.")
        sys.exit(ERROR_NO_VALID_LESSON_FILES)

    auth_token: str = get_auth_token(args.mavenseed_url, args.email, args.password)

    if not CACHE_FILE.exists():
        print("Cache file not found. Downloading and caching all data from Mavenseed.")
        cache_all_courses(args.mavenseed_url, auth_token)

    cached_data: dict = {}
    with open(CACHE_FILE) as f:
        cached_data = json.load(f)
    if not cached_data:
        print("Cache file is empty. Exiting.")
        sys.exit(ERROR_CACHE_FILE_EMPTY)

    # Get all courses and ensure we don't try to upload to a nonexistent course.
    courses: List[Course] = get_all_courses(args.mavenseed_url, auth_token)
    if args.list_courses:
        for course in courses:
            print(f"{course.id} - {course.title}")
        sys.exit(0)

    course_to_update: Course
    try:
        course_to_update = next(
            course
            for course in courses
            if args.course in (course.title, course.slug)
        )
    except StopIteration:
        print(
            "No course found with the given title or url slug: {desired_course}. Exiting."
        )
        sys.exit(ERROR_COURSE_NOT_FOUND)

    # Mapping lessons to their respective chapters.
    course_chapters: dict = cached_data[course_to_update.title]
    lessons_in_course: List[Lesson] = []
    for chapter in course_chapters:
        for lessons in chapter["lessons"]:
            lessons_in_course.append(Lesson(**lessons, content=""))

    # Create a data structure to turn file paths into a mapping of chapters to lessons.
    lessons_map: dict = {}
    for filepath in args.lesson_files:
        chapter_name: str = filepath.parent.name
        chapter_name = re.sub(r"[\-._]", " ", chapter_name)
        chapter_name = re.sub(r"\d+\.", "", chapter_name)
        chapter_name = chapter_name.capitalize()

        if not lessons_map.get(chapter_name):
            lessons_map[chapter_name] = []

        lesson_slug: str = filepath.stem.lower().replace(" ", "-")
        lessons_map[chapter_name].append((lesson_slug, filepath))

    # Find all chapters and lessons to create or to update.
    chapters_to_create: List[Chapter] = []
    lessons_to_create: List[Lesson] = []
    lessons_to_update: List[Lesson] = []
    for chapter_name in lessons_map:
        chapters_filter: filter = filter(
            lambda c: c.get("title") == chapter_name, course_chapters
        )
        matching_chapter: dict = next(chapters_filter, None)
        if not matching_chapter:
            chapters_to_create.append(NewChapter(title=chapter_name))

        for lesson_slug, filepath in lessons_map[chapter_name]:
            lessons_filter: filter = filter(
                lambda l: l.slug == lesson_slug, lessons_in_course
            )
            lesson = next(lessons_filter, None)
            if not lesson:
                lessons_to_create.append(NewLesson(slug=lesson_slug, filepath=filepath))
            else:
                lessons_to_update.append({lesson_slug: lesson.get("id")})
                
    # Upload all the files.
    # logging.info(f"Uploading {filepath} to Mavenseed")
    # upload_lesson(auth_token, filepath, args.course, args.token, args.overwrite)


if __name__ == "__main__":
    main()
