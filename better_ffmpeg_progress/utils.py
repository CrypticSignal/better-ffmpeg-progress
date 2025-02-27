import os


def line():
    width, _ = os.get_terminal_size()
    print("-" * width)


def print_with_prefix(prefix, message):
    print(f"{prefix}{message}")
