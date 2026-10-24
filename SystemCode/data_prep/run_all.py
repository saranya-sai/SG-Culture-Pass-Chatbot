"""Run the whole data preparation pipeline, raw snapshot -> event knowledge base.

Run from the 'Chatbot- Final Version' folder:
    python -m data_prep.run_all            (reuses saved OneMap results)
    python -m data_prep.run_all --refresh  (asks OneMap again for venues not yet found)
"""
import sys

from data_prep import (step1_load_and_filter, step2_clean, step3_rule_derived, step4_geocode,
                       step5_synthetic, step6_build_catalogue)


def main(refresh: bool = False) -> None:
    step1_load_and_filter.run()
    step2_clean.run()
    step3_rule_derived.run()
    step4_geocode.run(refresh=refresh)
    step5_synthetic.run()
    step6_build_catalogue.run()


if __name__ == "__main__":
    main(refresh="--refresh" in sys.argv)
