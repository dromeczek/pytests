import pytest
from pydantic import ValidationError
from epc.models import StartTrafficRequest
from epc.models import AttachUERequest

def test_start_traffic_request_converts_mbps_to_bps():
    request = StartTrafficRequest(protocol="tcp", Mbps=10)
    assert request.target_bps() == 10_000_000

def test_start_traffic_request_requires_exactly_one_throughput():
    with pytest.raises(ValidationError):
        StartTrafficRequest(protocol="tcp", Mbps=10, kbps=100)

def test_attach_ue_request_rejects_invalid_ue_id():
    with pytest.raises(ValidationError):
        AttachUERequest(ue_id=101)
def test_attach_ue_request_accepts_min_valid_ue_id():
    request = AttachUERequest(ue_id=0)

    assert request.ue_id == 0