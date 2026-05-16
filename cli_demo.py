"""Command-line demo for environments without Streamlit."""
from core.benefit_catalog import load_benefits
from core.demo_data import load_sample_profiles
from core.models import UserProfile
from core.report import make_markdown_report


def main() -> None:
    benefits = load_benefits()
    sample = load_sample_profiles()[0]
    profile = UserProfile.from_dict(sample["profile"])
    print(make_markdown_report(profile, benefits))


if __name__ == "__main__":
    main()
