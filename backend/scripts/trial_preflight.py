"""Fail fast before starting a trial API, worker, or migration container."""

from app.core.config import get_settings


def main() -> None:
    get_settings().validate_trial_runtime()


if __name__ == "__main__":
    main()
