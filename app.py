import streamlit as st
import requests
import re
from datetime import datetime, timedelta

def get_ical_events(url, exclude_keywords):
    """Wandelt die Rapla-HTML-URL in eine iCal-URL um und liest die Termine aus."""
    user_match = re.search(r'user=([^&]+)', url)
    file_match = re.search(r'file=([^&]+)', url)
    
    if not user_match or not file_match:
        st.error("Ungültige Rapla-URL")
        return []
        
    user = user_match.group(1)
    file = file_match.group(1)
    
    ical_url = f"https://rapla.dhbw.de/rapla?page=ical&user={user}&file={file}"
    
    try:
        response = requests.get(ical_url)
        response.raise_for_status()
        lines = response.text.splitlines()
        
        events = []
        in_event = False
        current_event = {}
        
        for line in lines:
            if line.startswith("BEGIN:VEVENT"):
                in_event = True
                current_event = {}
            elif line.startswith("END:VEVENT"):
                in_event = False
                summary = current_event.get("SUMMARY", "")
                skip = False
                for keyword in exclude_keywords:
                    if keyword.lower() in summary.lower():
                        skip = True
                        break
                        
                if not skip and "DTSTART" in current_event and "DTEND" in current_event:
                    events.append(current_event)
            elif in_event:
                if line.startswith("SUMMARY:"):
                    current_event["SUMMARY"] = line[8:]
                elif line.startswith("DTSTART"):
                    match = re.search(r':(\d{8}T\d{6})', line)
                    if match:
                        current_event["DTSTART"] = datetime.strptime(match.group(1), "%Y%m%dT%H%M%S")
                elif line.startswith("DTEND"):
                    match = re.search(r':(\d{8}T\d{6})', line)
                    if match:
                        current_event["DTEND"] = datetime.strptime(match.group(1), "%Y%m%dT%H%M%S")
                        
        return events
        
    except Exception as e:
        st.error(f"Fehler beim Laden von {user}: {e}")
        return []

st.set_page_config(page_title="DHBW Termin-Finder", page_icon="📅")
st.title("DHBW Termin-Finder 📅")
st.write("Wähle aus, wessen Kalender abgeglichen werden sollen.")

# Hardcoded Kalender mit den Vorgaben und Namen
all_calendars = {
    "Jannis": {
        "url": "https://rapla.dhbw.de/rapla/internal_calendar?user=muenzer@vw.ba.ba-ravensburg.de&file=TFE24-2",
        "exclude": ["künstliche Intelligenz", "STA Mercedes", "Quantentechnologie"]
    },
    "André": {
        "url": "https://rapla.dhbw.de/rapla/calendar?user=schraff.k%40vw.ba.ba-ravensburg.de&file=TFS24",
        "exclude": ["Kraftfahrzeuge", "Qualitätsmanagement", "Studienarbeit"]
    },
    "Ruben": {
        "url": "https://rapla.dhbw.de/rapla/calendar?user=brath%40vw.ba.ba-ravensburg.de&file=Stundenplan+TWI25-2",
        "exclude": []
    }
}

# --- UI: Auswahl der Personen ---
st.subheader("Wer soll Zeit haben?")
col1, col2, col3 = st.columns(3)
with col1:
    check_jannis = st.checkbox("Jannis", value=True)
with col2:
    check_andre = st.checkbox("André", value=True)
with col3:
    check_ruben = st.checkbox("Ruben", value=True)

# Sammle die ausgewählten Kalender
selected_calendars = []
if check_jannis: selected_calendars.append(all_calendars["Jannis"])
if check_andre: selected_calendars.append(all_calendars["André"])
if check_ruben: selected_calendars.append(all_calendars["Ruben"])

# --- UI: Optionen ---
show_individual_plans = st.checkbox("Zeige zusätzlich die Stundenpläne der ausgewählten Personen an")

# --- UI: Wochen-Auswahl ---
week_offset = st.slider(
    "Welche Woche möchtest du checken?", 
    min_value=0, 
    max_value=4, 
    value=0, 
    format="In %d Woche(n)"
)

if week_offset == 0:
    st.info("Gewählt: **Diese Woche**")
elif week_offset == 1:
    st.info("Gewählt: **Nächste Woche**")
else:
    st.info(f"Gewählt: **In {week_offset} Wochen**")

if st.button("Zeiten berechnen", type="primary"):
    if not selected_calendars:
        st.warning("Bitte wähle mindestens eine Person aus!")
    else:
        with st.spinner('Kalender werden abgeglichen...'):
            # Start der ausgewählten Woche berechnen (Montag)
            today = datetime.today()
            start_of_current_week = today - timedelta(days=today.weekday()) 
            start_of_current_week = start_of_current_week.replace(hour=8, minute=0, second=0, microsecond=0)
            start_of_target_week = start_of_current_week + timedelta(weeks=week_offset)
            end_of_target_week = start_of_target_week + timedelta(days=5) # Freitag Nacht

            all_blocked_slots = set()
            individual_events_text = { "Jannis": [], "André": [], "Ruben": [] }
            
            # Events für die ausgewählten Personen abrufen
            selected_names = []
            if check_jannis: selected_names.append("Jannis")
            if check_andre: selected_names.append("André")
            if check_ruben: selected_names.append("Ruben")

            for name in selected_names:
                cal = all_calendars[name]
                events = get_ical_events(cal["url"], cal["exclude"])
                
                for event in events:
                    start_dt = event['DTSTART']
                    end_dt = event['DTEND']
                    
                    # Nur Events berücksichtigen, die in der ausgewählten Woche liegen
                    if start_of_target_week <= start_dt < end_of_target_week:
                        # Für die Einzelanzeige speichern
                        individual_events_text[name].append({
                            "title": event.get("SUMMARY", "Termin"),
                            "start": start_dt,
                            "end": end_dt
                        })
                        
                        # In 15-Minuten-Blöcke für die Freistunden-Berechnung zerlegen
                        curr = start_dt
                        while curr < end_dt:
                            all_blocked_slots.add(curr)
                            curr += timedelta(minutes=15)
            
            # --- TEIL 1: Einzelne Stundenpläne anzeigen (falls gewünscht) ---
            if show_individual_plans:
                st.subheader("Stundenpläne (Ausgewählte Woche):")
                
                # Wir machen Tabs für jede ausgewählte Person
                tabs = st.tabs(selected_names)
                
                for i, name in enumerate(selected_names):
                    with tabs[i]:
                        person_events = individual_events_text[name]
                        if not person_events:
                            st.write("Keine Vorlesungen in dieser Woche!")
                        else:
                            # Nach Datum sortieren
                            person_events.sort(key=lambda x: x["start"])
                            
                            current_print_day = None
                            for ev in person_events:
                                ev_day = ev["start"].date()
                                if ev_day != current_print_day:
                                    st.markdown(f"**{ev['start'].strftime('%A, %d.%m.')}**")
                                    current_print_day = ev_day
                                st.write(f"- {ev['start'].strftime('%H:%M')} bis {ev['end'].strftime('%H:%M')}: {ev['title']}")
                
                st.divider() # Trennlinie

            # --- TEIL 2: Gemeinsame Freistunden berechnen ---
            st.subheader(f"Eure gemeinsamen Freistunden ({', '.join(selected_names)}):")
            
            tage = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag"]
            found_any = False
            
            for day in range(5):
                current_day = start_of_target_week + timedelta(days=day)
                free_periods = []
                current_free_start = None
                
                # Das Tagesraster abarbeiten (8 bis 23 Uhr)
                for hour in range(8, 23):
                    for minute in (0, 15, 30, 45):
                        slot = current_day.replace(hour=hour, minute=minute)
                        if slot not in all_blocked_slots:
                            if current_free_start is None:
                                current_free_start = slot
                        else:
                            if current_free_start is not None:
                                free_periods.append((current_free_start, slot))
                                current_free_start = None
                                
                if current_free_start is not None:
                    end_of_day = current_day.replace(hour=23, minute=0)
                    free_periods.append((current_free_start, end_of_day))
                    
                # Nur Zeitfenster anzeigen, die mindestens 45 Minuten lang sind
                valid_periods = [(s, e) for s, e in free_periods if (e - s).total_seconds() >= 2700]
                
                if valid_periods:
                    found_any = True
                    st.write(f"**{tage[day]}, {current_day.strftime('%d.%m.')}**")
                    for start, end in valid_periods:
                        st.success(f"✅ {start.strftime('%H:%M')} bis {end.strftime('%H:%M')} Uhr")
                        
            if not found_any:
                st.warning("In dieser Woche habt ihr in der gewählten Konstellation leider keine gemeinsamen Freistunden.")
