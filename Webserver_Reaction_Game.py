# Import necessary modules
import network
import socket
import time
import random
from machine import Pin
from neopixel import myNeopixel
import select

# Create LED objects on pins 'LED RED' and 'LED GREEN'
led_red = Pin(15, Pin.OUT)
led_green = Pin(16, Pin.OUT)

# Create Neopixel Lights
NUM_LEDS = 8
np = myNeopixel(NUM_LEDS, 20)

red = 0
green = 0
blue = 0

# Function for disco light wheel
def wheel(pos):
    global red, green, blue
    WheelPos = pos % 255
    if WheelPos < 85:
        red = (255 - WheelPos * 3)
        green = (WheelPos * 3)
        blue = 0
    elif WheelPos < 170:
        WheelPos -= 85
        red = 0
        green = (255 - WheelPos * 3)
        blue = (WheelPos * 3)
    else:
        WheelPos -= 170
        red = (WheelPos * 3)
        green = 0
        blue = (255 - WheelPos * 3)

# Function for the Disco Light Game:
def game():
    np.brightness(20)
    for i in range(255):
        for j in range(NUM_LEDS):
            wheel(i + j * 255 // NUM_LEDS)
            np.set_pixel(j, red, green, blue)
        np.show()
        time.sleep_ms(1)

    np.brightness(None)
    for i in range(NUM_LEDS):
        np.set_pixel(i, 0, 0, 0)
    np.show()

# Wi-Fi credentials
ssid = 'Lars'
password = '12345678'

# HTML template for the start page
def startpage():
    html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Pico Web Server Reaction Game</title>
            <meta charset="UTF-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1">
        </head>
        <body>
            <h1>Benutzernamen eingeben</h1>
        <form action="/" method="POST">
            <label for="username">Benutzername:</label>
            <input type="text" id="username" name="username">
            <input type="submit" value="Senden">
        </form>
        </body>
        </html>
        """
    return str(html)

# HTML template for the game page
def gamepage(status, username, client_ip):
    html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Pico Web Server Reaction Game</title>
            <meta charset="UTF-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1">
        </head>
        <body>
            <h1>Pico Web Server Reaction Game</h1><br>
            <h2>Moin {username}!</h2>
            <p>Du hast die IP {client_ip}</p><br><br>
            <h2>Spiel starten</h2>
            <p>Drücke auf Start um das Spiel zu starten:</p><br>
            <form action="./start">
                <input type="submit" value="Start" />
            </form><br><br>
            <h2>Reaktionsknopf</h2>
            <p>Sobald die Disco-Beleuchtung anspringt, drücke schnell auf den Button:</p><br>
            <form action="./reaction">
                <input type="submit" value="Das Licht ist an!" />
            </form><br>
            <p>{status}</p><br><br>
            <h2>Server trennen und Lampen aus</h2>
            <form action="./quit">
                <input type="submit" value="Quit" />
            </form>
        </body>
        </html>
        """
    return str(html)

# Spielerdaten anlegen
player_data = {}

# Globale Variablen für Spielzustand
game_in_progress = False
rand_wait = 0
start_time = 0
disco_on = False
led_green.value(0)
led_red.value(0)
reaction_times = {}
best_player_ever = None
best_time_ever = None

# Connect to WLAN
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(ssid, password)

# Wait for Wi-Fi connection
connection_timeout = 10
while connection_timeout > 0:
    if wlan.status() >= 3:
        break
    connection_timeout -= 1
    print('Warte auf WLAN-Verbindung...')
    time.sleep(1)

# Check if connection is successful
if wlan.status() != 3:
    raise RuntimeError('Keine Netzwerkverbindung möglich')
else:
    print('Verbindung mit WLAN erfolgreich!')
    network_info = wlan.ifconfig()
    print('IP address:', network_info[0])

# Set up socket and start listening
addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(addr)
s.listen()

print('Lausche auf', addr)

# Funktion: WLAN-Verbindung beenden und Lampen ausschalten
def wlanDisconnect():
    led_green.value(0)
    led_red.value(0)
    wlan = network.WLAN(network.STA_IF)
    if wlan.isconnected():
        wlan.disconnect()
        time.sleep(2)
        print('WLAN-Verbindung beendet')
    else:
        print('Keine WLAN-Verbindung')

def parse_post_data(data):
    """Extrahiere die POST-Daten (Formulardaten)"""
    try:
        post_data = data.split('\r\n\r\n')[1]  # POST-Daten sind nach einem doppelten CRLF
        params = post_data.split('&')  # Name-Wert-Paare
        form_data = {}
        for param in params:
            key, value = param.split('=')
            form_data[key] = value
        return form_data
    except Exception as e:
        print("Fehler beim Parsen der POST-Daten:", e)
        return {}

# Funktion, um den Client mit der schnellsten Reaktionszeit im aktuellen Spiel zu ermitteln
def find_fastest_player():
    global best_player_ever, best_time_ever
    
    if reaction_times:
        fastest_client_ip = min(reaction_times, key=reaction_times.get)  # Die kleinste Reaktionszeit
        fastest_username = player_data.get(fastest_client_ip, "Unbekannt")
        fastest_time = reaction_times[fastest_client_ip]

        # Aktualisieren, wenn die neue Zeit besser ist als die bisherige Bestzeit
        if best_time_ever is None or fastest_time < best_time_ever:
            best_time_ever = fastest_time
            best_player_ever = fastest_username
        
        return fastest_username, fastest_time
    return None, None

# Main loop to listen for connections
while True:
    try:
        readable, _, _ = select.select([s], [], [], 1)  # 1 Sekunde Timeout

        if s in readable:
            conn, addr = s.accept()
            print('Verbindung hergestellt von', addr)

            # Receive and parse the request
            request = conn.recv(1024).decode('utf-8')
            print("Request:\n", request)

            # IP-Adresse des Clients ermitteln
            client_ip = addr[0]

            # Überprüfen, ob eine POST-Anfrage vorliegt (Benutzername eingeben)
            if "POST" in request:
                form_data = parse_post_data(request)
                username = form_data.get('username', 'Unbekannt')

                # In Spielerdaten speichern
                player_data[client_ip] = username

                # Spielseite anzeigen
                response = gamepage("", username, client_ip)

            elif client_ip in player_data:
                username = player_data[client_ip]
                status = ""

                try:
                    request = request.split()[1]
                    print('Request:', request)
                except IndexError:
                    pass

                # Wenn ein Client das Spiel startet
                if request == '/start?':
                    led_green.value(0)
                    led_red.value(0)
                    print("\nDas Spiel beginnt\n")

                    # Spielzustand global aktualisieren
                    rand_wait = random.randint(5000, 10000)  # Zufällige Wartezeit in Millisekunden
                    start_time = time.ticks_ms()  # Startzeit in Millisekunden
                    game_in_progress = True
                    disco_on = False
                    reaction_times = {}  # Reaktionszeiten zurücksetzen
                    fastest_username = ""
                    fastest_time = None
                    print(f"Rand wait time: {rand_wait / 1000} seconds")

                # Wenn ein Client den Button "Das Licht ist an!" drückt
                elif request == '/reaction?':
                    current_time = time.ticks_ms()  # Aktuelle Zeit in Millisekunden

                    if not game_in_progress:
                        status = "Kein Spiel läuft!"
                    elif not disco_on and time.ticks_diff(current_time, start_time) < rand_wait:
                        # Zu früh gedrückt, bevor das Discolicht anging
                        led_red.value(1)
                        status = "Zu früh!"
                    elif disco_on and client_ip not in reaction_times:
                        # Korrekte Reaktion, nachdem die Lichter angingen
                        reaction_time = time.ticks_diff(current_time, start_time + rand_wait)  # Zeitdifferenz in Millisekunden
                        reaction_times[client_ip] = reaction_time / 1000 - 1.5  # In Sekunden umrechnen

                        led_green.value(1)
                        status = f"Treffer! Reaktionszeit: {reaction_time / 1000 - 1.5:.3f} Sekunden<br>"

                        # Den schnellsten Spieler ermitteln
                        fastest_username, fastest_time = find_fastest_player()
                        if fastest_username:
                            status += f" <br>Schnellster Spieler: {fastest_username} mit {fastest_time:.3f} Sekunden"
                        if best_player_ever and best_time_ever is not None:
                            status += f" <br><br>Bester Spieler bisher: {best_player_ever} mit {best_time_ever:.3f} Sekunden"

                elif request == '/quit?':
                    wlanDisconnect()

                response = gamepage(status, username, client_ip)

            else:
                # Startseite anzeigen, wenn kein Benutzername eingegeben wurde
                response = startpage()

            conn.send('HTTP/1.0 200 OK\r\nContent-type: text/html\r\n\r\n')
            conn.send(response)
            conn.close()

        # Überprüfen, ob die Disco-Lichter eingeschaltet werden sollen
        if game_in_progress and not disco_on and time.ticks_diff(time.ticks_ms(), start_time) >= rand_wait:
            print("Disco-Lichter an!")
            disco_on = True
            game()  # Disco-Lichter starten

    except OSError as e:
        conn.close()
        print('Verbindung getrennt:', e)