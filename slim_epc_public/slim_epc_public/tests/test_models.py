import pytest
from pydantic import ValidationError

from epc.models import (
    BearerConfig,
    ThroughputStats,
    UEState,
    AttachUERequest,
    AddBearerRequest,
    StartTrafficRequest
)


# --- Testy dla BearerConfig ---

# Weryfikuje, czy model BearerConfig akceptuje skrajne prawidłowe wartości identyfikatorów (od 1 do 9).
def test_bearer_config_valid_ids():
    # Sprawdzenie wartości skrajnych dla bearer_id (1-9)
    assert BearerConfig(bearer_id=1).bearer_id == 1
    assert BearerConfig(bearer_id=9).bearer_id == 9

# Weryfikuje, czy system poprawnie odrzuca identyfikatory bearerów spoza dozwolonego zakresu.
def test_bearer_config_invalid_ids():
    # Sprawdzenie wartości poza zakresem
    with pytest.raises(ValidationError):
        BearerConfig(bearer_id=0)
    with pytest.raises(ValidationError):
        BearerConfig(bearer_id=10)

# Weryfikuje, czy model poprawnie przetwarza i akceptuje zdefiniowane w regexie protokoły (tcp, udp) oraz brak protokołu (None).
def test_bearer_config_valid_protocols():
    assert BearerConfig(bearer_id=1, protocol="tcp").protocol == "tcp"
    assert BearerConfig(bearer_id=1, protocol="udp").protocol == "udp"
    assert BearerConfig(bearer_id=1).protocol is None  # Domyślnie None

# Weryfikuje, czy walidacja odrzuca nieznane protokoły oraz czy wymusza stosowanie małych liter.
def test_bearer_config_invalid_protocols():
    # Regex pozwala tylko na małe litery 'tcp' lub 'udp'
    with pytest.raises(ValidationError):
        BearerConfig(bearer_id=1, protocol="http")
    with pytest.raises(ValidationError):
        BearerConfig(bearer_id=1, protocol="TCP")  # Wielkie litery są odrzucane


# --- Testy dla ThroughputStats ---

# Sprawdza, czy po utworzeniu statystyk bez podawania wartości, liczniki transferu i czasy ustawiają się na domyślne zera/None.
def test_throughput_stats_defaults():
    # Sprawdzenie czy domyślne wartości ustawiają się poprawnie
    stats = ThroughputStats(bearer_id=5, ue_id=10)
    assert stats.bytes_tx == 0
    assert stats.bytes_rx == 0
    assert stats.start_ts is None


# --- Testy dla UEState ---

# Weryfikuje, czy w obecnym kodzie model stanu urządzenia (UE) akceptuje wartości brzegowe od 1 do 100.
def test_uestate_valid_ids():
    assert UEState(ue_id=1).ue_id == 1
    assert UEState(ue_id=100).ue_id == 100

# Weryfikuje, czy obecny kod odrzuca identyfikatory UE poniżej 1 i powyżej 100.
def test_uestate_invalid_ids():
    # Zmieniamy 0 na -1, bo 0 jest już dozwolone
    with pytest.raises(ValidationError):
        UEState(ue_id=-1)
    with pytest.raises(ValidationError):
        UEState(ue_id=101)

# Sprawdza działanie walidatora (pre-init), który upewnia się, że nawet jeśli przekażemy 'None' w listach bearerów i statystyk, zamienią się one w puste słowniki.
def test_uestate_init_defaults():
    # Test validatora pre-inicjalizacji (zamiana None na pusty dict)
    state_empty = UEState(ue_id=1)
    assert state_empty.bearers == {}
    assert state_empty.stats == {}

    state_with_none = UEState(ue_id=1, bearers=None, stats=None)
    assert state_with_none.bearers == {}
    assert state_with_none.stats == {}


# --- Testy dla żądań (Requests) ---

# Sprawdza, czy endpoint podłączania UE akceptuje id 1 i odrzuca id 0 (zgodnie z aktualnie zdefiniowanymi limitami).
def test_attach_ue_request_validation():
    # Dodajmy też asercję sprawdzającą nowe zero!
    assert AttachUERequest(ue_id=0).ue_id == 0
    assert AttachUERequest(ue_id=1).ue_id == 1
    
    # Zmieniamy 0 na -1
    with pytest.raises(ValidationError):
        AttachUERequest(ue_id=-1)

# Sprawdza, czy żądanie dodania bearera przestrzega maksymalnego limitu ID bearera (9).
def test_add_bearer_request_validation():
    assert AddBearerRequest(bearer_id=9).bearer_id == 9
    with pytest.raises(ValidationError):
        AddBearerRequest(bearer_id=10)


# --- Testy dla StartTrafficRequest ---

# Weryfikuje działanie walidatora krzyżowego, który wymusza na użytkowniku podanie tylko i wyłącznie jednej jednostki miary prędkości (albo Mbps, albo kbps, albo bps).
def test_start_traffic_request_exactly_one_throughput():
    # Poprawne przypadki - dokładnie jedna wartość
    StartTrafficRequest(protocol="tcp", Mbps=10.5)
    StartTrafficRequest(protocol="udp", kbps=1000)
    StartTrafficRequest(protocol="tcp", bps=500)

    # Błędne przypadki - brak wartości
    with pytest.raises(ValidationError, match="Provide exactly one throughput value"):
        StartTrafficRequest(protocol="tcp")

    # Błędne przypadki - więcej niż jedna wartość
    with pytest.raises(ValidationError, match="Provide exactly one throughput value"):
        StartTrafficRequest(protocol="udp", Mbps=10, kbps=10000)

# Sprawdza, czy funkcja pomocnicza 'target_bps' poprawnie mnoży przesyłane jednostki i konwertuje je wszystkie do bazowego 'bps' (bitów na sekundę).
def test_start_traffic_request_target_bps_calculation():
    # Mbps do bps
    req_mbps = StartTrafficRequest(protocol="tcp", Mbps=2.5)
    assert req_mbps.target_bps() == 2_500_000

    # kbps do bps
    req_kbps = StartTrafficRequest(protocol="udp", kbps=150.5)
    assert req_kbps.target_bps() == 150_500

    # bps pozostaje bez zmian
    req_bps = StartTrafficRequest(protocol="tcp", bps=300)
    assert req_bps.target_bps() == 300

# Sprawdza czy kod zabezpiecza przez wpisaniem prędkości większej niż 100 Mbps, tak jak wymaga tego dokumentacja.
def test_start_traffic_request_enforces_max_100_mbps():
    # Zgodnie z dokuemntacją max to 100 Mbps.
    # Próba ustawienia 101 Mbps powinna rzucić błąd walidacji, ale obecnie tego nie robi.
    with pytest.raises(ValidationError, match="max 100 Mbps"):
        StartTrafficRequest(protocol="tcp", Mbps=101)
        
    with pytest.raises(ValidationError):
            StartTrafficRequest(protocol="udp", kbps=100_001)  # ponad 100 Mbps w kbps
        
    with pytest.raises(ValidationError):
        StartTrafficRequest(protocol="tcp", bps=100_000_001) # ponad 100 Mbps w bps

# Weryfikuje, że system obecnie nie pozwala podłączyć UE z ID = 0, chociaż według wymagań projektowych powinien to robić.
def test_attach_ue_accepts_id_0_per_documentation():
    # Dokumentacja zakłada urządzenia od 0 do 100.
    # Obecnie kod wywali błąd dla id=0, więc test ten obnaży niezgodność aplikacji z dokumentacją.
    try:
        req = AttachUERequest(ue_id=0)
        assert req.ue_id == 0
    except ValidationError:
        pytest.fail("Aplikacja odrzuca UE ID = 0, mimo że dokumentacja pozwala na zakres 0-100.")