import socket
import time

# Funkcja do konwersji współrzędnych NMEA na stopnie dziesiętne z uwzględnieniem liczby cyfr w stopniach
def nmea_to_decimal(degree_minute, direction, degree_length):
    if degree_minute == "":
        return None
    degrees = int(degree_minute[:degree_length])  # Wydzielenie części stopni
    minutes = float(degree_minute[degree_length:])  # Reszta to minuty
    decimal = degrees + (minutes / 60)  # Przeliczamy na stopnie dziesiętne
    if direction in ['S', 'W']:  # Ujemna wartość dla kierunków S i W
        decimal = -decimal
    return decimal

# Funkcja do generowania pliku KML
def create_kml_file(latitude, longitude, altitude):
    if latitude is None or longitude is None:
        print("Brak poprawnych danych GPS. Plik KML nie zostanie utworzony.")
        return
    
    kml_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Placemark>
    <name>RTK 0</name>
    <description>Pozycja na podstawie depeszy GNGGA</description>
    <Point>
      <coordinates>{longitude},{latitude},{altitude}</coordinates>
    </Point>
  </Placemark>
</kml>
'''
    # Zapis do pliku KML
    with open("pozycja_gps.kml", "w") as file:
        file.write(kml_content)

    print("Plik KML został zapisany jako 'pozycja_gps.kml'. Możesz go teraz zaimportować do Google Earth.")

# Adres serwera UDP (serwer, z którym się łączymy)
UDP_IP = "153.19.108.122"  # Adres serwera (upewnij się, że poprawny)
UDP_PORT = 7000  # Port serwera

# Tworzenie socketu UDP
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.settimeout(5)  # Ustawienie timeoutu na 5 sekund dla socketu

# Wysyłanie wiadomości "GET" co 1 sekundę
while True:
    try:
        message = "GET"
        sock.sendto(message.encode('utf-8'), (UDP_IP, UDP_PORT))
        print(f"Wysłano wiadomość 'GET' do serwera {UDP_IP}:{UDP_PORT}")

        # Odbieranie depeszy NMEA od serwera
        data, addr = sock.recvfrom(1024)  # Odbieranie maksymalnie 1024 bajtów
        nmea_sentence = data.decode('utf-8')
        print(f"Odebrano depeszę NMEA: {nmea_sentence}")

        # Sprawdzenie, czy to depesza GNGGA
        if nmea_sentence.startswith("$GNGGA"):
            parts = nmea_sentence.split(',')

            # Szerokość geograficzna (latitude)
            latitude_nmea = parts[2]
            latitude_direction = parts[3]

            # Długość geograficzna (longitude)
            longitude_nmea = parts[4]
            longitude_direction = parts[5]

            # Wysokość nad poziomem morza
            altitude = parts[9] if parts[9] != "" else "0"  # Domyślnie wysokość 0, jeśli brak danych

            # Konwersja współrzędnych z uwzględnieniem liczby cyfr w stopniach
            latitude = nmea_to_decimal(latitude_nmea, latitude_direction, 2)  # 2 cyfry dla szerokości
            longitude = nmea_to_decimal(longitude_nmea, longitude_direction, 3)  # 3 cyfry dla długości

            # Tworzenie pliku KML z otrzymanych współrzędnych
            create_kml_file(latitude, longitude, altitude)

    except socket.timeout:
        print("Serwer nie odpowiedział w ciągu 5 sekund. Próba ponownego wysłania...")

    except Exception as e:
        print(f"Wystąpił błąd: {e}")

    # Opóźnienie 1 sekundy przed ponownym wysłaniem wiadomości
    time.sleep(1)
