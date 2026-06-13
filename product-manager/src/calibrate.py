#!/usr/bin/env python3
"""Weekly calibration: check if the feedback mechanism is healthy."""

import sys
from datetime import datetime, timedelta
from journal import init, calibrate


def main():
    conn = init()
    end = datetime.utcnow().isoformat()
    start = (datetime.utcnow() - timedelta(days=7)).isoformat()

    report = calibrate(conn, start, end)

    if "error" in report:
        print(report["error"])
        sys.exit(0)

    print("=== Weekly Feedback Mechanism Calibration ===")
    print(f"Period: {report['period']}")
    print(f"UX samples: {report['total_ux_samples']}")
    print(f"Gate-UX consistency: {report['consistency_rate']:.1%}")
    print(f"False positives (Gate PASS, UX bad): {report['false_positive']}")
    print(f"False negatives (Gate FAIL, UX OK): {report['false_negative']}")
    print(f"Health: {report['health']}")

    if report['health'] == 'CRITICAL':
        print("\nACTION REQUIRED: consistency < 70%. Gate needs redesign.")
        print("1. Review false positive cases -> find Gate blind spots -> update AC")
        print("2. Review false negative cases -> Gate may be too strict -> adjust thresholds")
        sys.exit(1)
    elif report['health'] == 'WARNING':
        print("\nWARNING: consistency < 85%. Monitor trend closely.")
    else:
        print("\nHEALTHY: feedback mechanism is working correctly.")

    # Show chain integrity
    from journal import verify_chain
    chain = verify_chain(conn)
    print(f"\nJournal integrity: {chain['integrity']} ({chain['total_entries']} entries)")
    if chain['integrity'] == 'BROKEN':
        print(f"BROKEN at: {chain['broken_at']}")
        sys.exit(2)


if __name__ == "__main__":
    main()
