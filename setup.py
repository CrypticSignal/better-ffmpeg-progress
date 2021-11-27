import setuptools

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setuptools.setup(
    name="better-ffmpeg-progress",
    version="2.0.0",
    author="GitHub.com/CrypticSignal",
    author_email="theaudiophile@outlook.com",
    description="Run FFmpeg & see percentage progress + ETA.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/CrypticSignal/better-ffmpeg-progress",
    packages=["better_ffmpeg_progress"],
    install_requires=["ffmpeg-python", "tqdm"],
    python_requires=">=3.6",
    keywords=["ffmpeg", "progress"],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ]
)