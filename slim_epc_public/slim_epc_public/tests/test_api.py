import pytest
from fastapi.testclient import TestClient
from main import app

# Tworzymy klienta testowego FastAPI
client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_state():
    """Automatycznie resetuje stan bazy danych i czyszczenie zadań generatora ruchu przed każdym testem."""
    client.post("/reset")
    yield


# --- TESTY ENDPOINTÓW UE ---

@pytest.mark.parametrize("ue_id", [1, 50, 100])
def test_attach_ue_endpoint_valid_ids(ue_id):
    """Weryfikacja poprawnego podłączenia UE (zakres 1-100) przez API."""
    response = client.post("/ues", json={"ue_id": ue_id})
    assert response.status_code == 200
    assert response.json() == {"status": "attached", "ue_id": ue_id}


@pytest.mark.parametrize("ue_id", [0, 101, -1])
def test_attach_ue_endpoint_invalid_ids(ue_id):
    """Weryfikacja odrzucenia ID spoza zakresu (FastAPI/Pydantic zwraca status 422 Unprocessable Entity)."""
    response = client.post("/ues", json={"ue_id": ue_id})
    assert response.status_code == 422


def test_attach_duplicate_ue_returns_400():
    """Próba podłączenia już istniejącego UE powinna zwrócić błąd domeny 400."""
    client.post("/ues", json={"ue_id": 1})
    response = client.post("/ues", json={"ue_id": 1})
    assert response.status_code == 400
    assert "already attached" in response.json()["detail"]


def test_get_ue_state_and_default_bearer():
    """Weryfikacja pobierania stanu UE i upewnienie się, że domyślny bearer 9 istnieje w strukturze."""
    client.post("/ues", json={"ue_id": 1})
    response = client.get("/ues/1")
    assert response.status_code == 200
    
    data = response.json()
    assert data["ue_id"] == 1
    
    # Bezpieczne sprawdzenie obecności bearera 9 niezależnie od typu klucza (str lub int)
    bearers_keys = [str(k) for k in data["bearers"].keys()]
    assert "9" in bearers_keys


def test_detach_ue_endpoint():
    """Weryfikacja usuwania (odłączania) UE."""
    client.post("/ues", json={"ue_id": 1})
    response = client.delete("/ues/1")
    assert response.status_code == 200
    assert response.json() == {"status": "detached", "ue_id": 1}


# --- TESTY ENDPOINTÓW BEARER ---

@pytest.mark.parametrize("bearer_id", [1, 5, 8])
def test_add_bearer_endpoint_valid_range(bearer_id):
    """Weryfikacja poprawnego dodawania dodatkowych bearerów (1-9)."""
    client.post("/ues", json={"ue_id": 1})
    response = client.post("/ues/1/bearers", json={"bearer_id": bearer_id})
    assert response.status_code == 200
    assert response.json() == {"status": "bearer_added", "ue_id": 1, "bearer_id": bearer_id}


def test_add_bearer_out_of_range_returns_422():
    """Dodanie bearera 10 powinno zostać zablokowane na poziomie walidacji schematu (422)."""
    client.post("/ues", json={"ue_id": 1})
    response = client.post("/ues/1/bearers", json={"bearer_id": 10})
    assert response.status_code == 422


def test_cannot_delete_default_bearer_9():
    """Weryfikacja ochrony domyślnego bearera 9 przed usunięciem (błąd domeny 400)."""
    client.post("/ues", json={"ue_id": 1})
    response = client.delete("/ues/1/bearers/9")
    assert response.status_code == 400
    assert response.json()["detail"] == "Cannot remove default bearer"


# --- TESTY ENDPOINTÓW GENERATORA RUCHU (TRAFFIC) ---

def test_start_traffic_success():
    """Weryfikacja poprawnego uruchomienia symulacji ruchu na bearerze."""
    client.post("/ues", json={"ue_id": 1})
    response = client.post("/ues/1/bearers/9/traffic", json={"protocol": "tcp", "Mbps": 10})
    assert response.status_code == 200
    assert response.json()["status"] == "traffic_started"
    assert response.json()["target_bps"] == 10_000_000


def test_start_traffic_clashing_units_returns_422():
    """Weryfikacja, że podanie wielu jednostek naraz (Mbps i kbps) skutkuje błędem walidacji Pydantic v2."""
    client.post("/ues", json={"ue_id": 1})
    response = client.post("/ues/1/bearers/9/traffic", json={"protocol": "tcp", "Mbps": 10, "kbps": 1000})
    assert response.status_code == 422
    assert "exactly one throughput value" in response.json()["detail"][0]["msg"]


def test_start_traffic_invalid_protocol():
    """Weryfikacja odrzucenia niepoprawnego protokołu (akceptowane są tylko tcp/udp)."""
    client.post("/ues", json={"ue_id": 1})
    response = client.post("/ues/1/bearers/9/traffic", json={"protocol": "http", "Mbps": 5})
    assert response.status_code == 422


def test_stop_traffic_endpoint():
    """Weryfikacja poprawnego zatrzymania ruchu."""
    client.post("/ues", json={"ue_id": 1})
    client.post("/ues/1/bearers/9/traffic", json={"protocol": "udp", "Mbps": 5})
    response = client.delete("/ues/1/bearers/9/traffic")
    assert response.status_code == 200
    assert response.json() == {"status": "traffic_stopped", "ue_id": 1, "bearer_id": 9}


def test_get_aggregated_stats():
    """Weryfikacja endpointu ze statystykami zbiorczymi /ues/stats."""
    client.post("/ues", json={"ue_id": 1})
    response = client.get("/ues/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["scope"] == "all"
    assert data["ue_count"] == 1