from .cli import MisskeyCLI


def main():
    try:
        MisskeyCLI().cmdloop()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
