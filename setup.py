from pathlib import Path

from setuptools import find_packages, setup

setup(
    name="talk-to-blog",
    version="0.1.0",
    description="Convert conference talk transcripts into blog posts",
    long_description=Path("README.md").read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    author="Ryan Johnson",
    author_email="ryanleejwebdev@gmail.com",
    url="https://github.com/ryan258/talk-to-blog",
    packages=find_packages(),
    python_requires=">=3.8",
    entry_points={
        "console_scripts": [
            "talk-to-blog=talk_to_blog.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: Console",
        "Intended Audience :: Education",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Text Processing :: General",
        "Topic :: Text Processing :: Markup",
    ],
)
