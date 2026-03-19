"""Entry point for `python -m switchboard` or `switchboard` CLI."""

from .app import SwitchboardApp


def main():
    SwitchboardApp().run()


if __name__ == "__main__":
    main()
