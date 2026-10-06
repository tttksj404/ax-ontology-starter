from ax_starter.bootstrap import example_log
from ax_starter.process_metrics import process_metrics


def test_bottleneck_when_wait_exceeds_processing() -> None:
    # Given
    log = example_log()
    # When
    report = process_metrics(log)
    # Then
    assert report.bottleneck_step == "step-2"
    assert report.case_count == 3
    assert report.median_lead_minutes == 32
    assert report.handoff_count == 3
    assert report.stages[1].wait_share == 0.8
    assert report.synthetic is True
