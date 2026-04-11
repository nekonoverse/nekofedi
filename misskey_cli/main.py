from .migrate import run_upgrade
from .i18n import init_language
from .cli import MisskeyCLI


def main():
    run_upgrade()
    init_language()
    try:
        MisskeyCLI().cmdloop()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
