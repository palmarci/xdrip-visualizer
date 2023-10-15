import argparse
import datetime
import os
import sqlite3
import tempfile
import zipfile

import plotly.graph_objs as ply
import requests

output_filename = 'xdrip_database.html'
offset_min_difference = 15 # in minutes
max_display = 22

class Measurement:
	def __init__(self, id, value, timestamp):
		self.id = id
		self.value = value
		self.timestamp = timestamp

	def __repr__(self):
		return f'Measurement(id: {self.id}, timestamp:{self.timestamp}, value: {self.value})'

	def __lt__(self, other):
		 return self.timestamp < other.timestamp

class Insulin:
	def __init__(self, id, timestamp, value, is_long_type):
		self.id = id
		self.timestamp = timestamp
		self.value = int(value)
		self.is_long_type = is_long_type

	def __repr__(self):
		return f'Insulin(id: {self.id}, timestamp:{self.timestamp}, value: {self.value}, is long: {self.is_long_type})'

	def __lt__(self, other):
		 return self.timestamp < other.timestamp

class Note:
	def __init__(self, id, timestamp, text):
		self.id = id
		self.timestamp = timestamp
		self.text = text

	def __repr__(self):
		return f'Note(id: {self.id}, timestamp:{self.timestamp}, text: {self.text})'

	def __lt__(self, other):
		 return self.timestamp < other.timestamp

class Meal:
	def __init__(self, id, timestamp, ch):
		self.id = id
		self.timestamp = timestamp
		self.ch = int(ch)

	def __repr__(self):
		return f'Meal(id: {self.id}, timestamp:{self.timestamp}, ch: {self.ch})'

	def __lt__(self, other):
		 return self.timestamp < other.timestamp

def create_graphs(data, last_days, min_acceptable_bg, max_acceptable_bg, no_widescreen):
	measurements, treatments, meals, notes = data
	today = datetime.datetime.now().date()
	start_date = today - datetime.timedelta(days=last_days - 1)
	
	measurements = [m for m in measurements if m.timestamp.date() >= start_date]
	treatments = [t for t in treatments if t.timestamp.date() >= start_date]

	data_by_date = {}
	for measurement in measurements:
		date_str = measurement.timestamp.strftime('%Y-%m-%d')
		if date_str not in data_by_date:
			data_by_date[date_str] = {'timestamps': [], 'values': []}
		data_by_date[date_str]['timestamps'].append(measurement.timestamp)
		data_by_date[date_str]['values'].append(measurement.value)

	plotly_js_url = 'https://cdn.plot.ly/plotly-latest.min.js'
	plotlyjs_req = requests.get(plotly_js_url)

	print("downloading latest plotly library...")
	if plotlyjs_req.status_code != 200:
		raise Exception("Could not download and bake in plotly js library.")
		
	html_content = f"""
	<!DOCTYPE html>
	<html>
	<head>
		<title>xDrip Database Viewer</title>
		<script>
			{plotlyjs_req.text}
		</script>
	</head>
	<body>
	<center>
	<h1>xDrip Database Viewer</h1>
	"""

	print("calculating averages...")
	avg_values = [round(sum(data_by_date[date]['values']) / len(data_by_date[date]['values']), 1) for date in data_by_date]
	avg_bg = round(sum(avg_values) / len(avg_values), 1)
	
	if len(avg_values) == 0 or avg_bg is None or avg_bg == 0:
		raise Exception("Could not calculate average blood sugar values. Perhaps the minimum insulin values are not set correctly? Run with --help to get more info.")
	
	html_content += f"<div>Average Blood Glucose: {avg_bg} mmol/l for the last {last_days} days<br>"
	html_content += f"Generated on {datetime.datetime.today().strftime('%Y-%m-%d %H:%M:%S')}</div><br><br>"

	#TODO add notes and meals
	print("creating graphs...")

	for date_str in sorted(data_by_date.keys(), reverse=True):  
		measurements = data_by_date[date_str]
		sugar_trace_color = ['green' if min_acceptable_bg <= val <= max_acceptable_bg else 'red' for val in measurements['values']]
		sugar_trace = ply.Scatter(name="Bloog Sugar", x=measurements['timestamps'], y=measurements['values'], mode='lines', marker={'color': sugar_trace_color}, line={'color': 'black'}, showlegend=False) #lines+markers
		min_line = ply.Scatter(x=measurements['timestamps'], y=[min_acceptable_bg] * len(measurements['timestamps']), mode='lines', line={'color': 'red', "dash":"dot"}, name='Min', showlegend=False)
		max_line = ply.Scatter(x=measurements['timestamps'], y=[max_acceptable_bg] * len(measurements['timestamps']), mode='lines', line={'color': 'red',"dash":"dot"}, name=f'Max', showlegend=False)
		fig = ply.Figure(data=[sugar_trace, min_line, max_line])

		for i in range(0, 24, 3):
			line_x = [measurements['timestamps'][0] + datetime.timedelta(hours=i), measurements['timestamps'][0] + datetime.timedelta(hours=i)]
			fig.add_shape(
				ply.layout.Shape(
					type='line',
					x0=line_x[0],
					x1=line_x[1],
					y0=0,
					y1=max_display - 1,
					line=dict(color='lightgrey', width=1),
					xref='x',
					yref='y'
				)
			)

		treatment_values = [t for t in treatments if t.timestamp.strftime('%Y-%m-%d') == date_str]

		for i, treatment in enumerate(treatment_values):
			color = 'green' if treatment.is_long_type else 'blue'
			fig.add_shape(ply.layout.Shape(
				type='line',
				x0=treatment.timestamp,
				x1=treatment.timestamp,
				y0=0,
				y1=25,
				line=dict(color=color),
				xref='x',
				yref='y',
				layer="below"
			))

			fig.add_annotation(
				text=str(treatment.value),
				x=treatment.timestamp,
				y=1,
				showarrow=True,
				font=dict(color=color, size=18, family="Arial"),
				yshift= -20 if treatment.is_long_type else 0, 
		 	
			)

		for i, meal in enumerate(meals):
			closest_index = min(
				range(len(measurements['timestamps'])),
				key=lambda i: abs(measurements['timestamps'][i] - meal.timestamp)
			)
			if 0 <= closest_index < len(measurements['values']):
				time_difference = abs(measurements['timestamps'][closest_index] - meal.timestamp).total_seconds() / 60
				current_color = 'darkorange' if meal.ch != 1 else "red"
				if time_difference <= 5:
					location = 11 if closest_index == 0 else measurements['values'][closest_index] + 3
					if (max_acceptable_bg - 1) < location < max_acceptable_bg:
						location += 1

					fig.add_trace(
						ply.Scatter(
							x=[meal.timestamp],
							y=[location],
							mode='markers+text',
							text="<b>" + f"{meal.ch} CH" if meal.ch != 1 else "Sugar" + "</b>",
							textposition="top center",
							marker=dict(size=20, color=current_color),
							showlegend=False,
							textfont=dict(color=current_color, family="Arial", size=16)
						)
					)

		html_content += f'<div style="border: 2px solid black"><h2>Date: {date_str}</h2>'

		for note in notes:
			if note.timestamp.strftime('%Y-%m-%d') == date_str:
				html_content += f"<p>{note.timestamp.strftime('%H:%M')} - {note.text}</p>"


		fig.update_yaxes(showgrid=True, gridcolor="lightgrey", zeroline=False, showline=False, dtick=1)
		fig.update_layout(title_text=f'', xaxis_title='Time', yaxis_title='Blood Glucose (mmol/l)')
		fig.update_xaxes(type='date')
		fig.update_yaxes(range=[0, max_display])

		if no_widescreen:
			fig.update_layout(width=1024, height=768)
		else:
			fig.update_layout(width=1600, height=900)

		html_content += fig.to_html(full_html=False, include_plotlyjs=False)  
		html_content += "</div><br>"


	html_content += """
	</center>
	</body>
	</html>
	"""

	print(f'writing html file to {output_filename}')
	with open(output_filename, 'w') as html_file:
		html_file.write(html_content)

def load_data(zip_path):
		print(f"loading data...")
		with zipfile.ZipFile(zip_path, 'r') as archive:
			sqlite_file_name = next((file_name for file_name in archive.namelist() if file_name.endswith('.sqlite')), None)
			if sqlite_file_name:
				with archive.open(sqlite_file_name) as sqlite_file:
					with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
						tmp_file.write(sqlite_file.read())
						tmp_file_path = tmp_file.name
					conn = sqlite3.connect(tmp_file_path)
					cursor = conn.cursor()
					measurements = []
					treatments = []
					notes = []
					meals = []
					cursor.execute("SELECT _id, calculated_value, timestamp FROM BgReadings")

					for row in cursor.fetchall():
						id, value, millis_timestamp = row
						seconds_timestamp = millis_timestamp / 1000.0  
						timestamp = datetime.datetime.fromtimestamp(seconds_timestamp)
						measurements.append(Measurement(id, round(float(int(value) / 18), 1), timestamp))
					cursor.execute("SELECT _id, mgdl, timestamp FROM BloodTest")

					for row in cursor.fetchall():
						id, value, millis_timestamp = row
						seconds_timestamp = millis_timestamp / 1000.0  
						timestamp = datetime.datetime.fromtimestamp(seconds_timestamp)
						manual = Measurement(id, round(float(int(value) / 18), 1), timestamp)
						measurements.append(manual)
					cursor.execute("SELECT _id, timestamp, insulin FROM Treatments")

					for row in cursor.fetchall():
						id, millis_timestamp, insulin = row
						seconds_timestamp = millis_timestamp / 1000.0  
						timestamp = datetime.datetime.fromtimestamp(seconds_timestamp)
						if insulin is not None and insulin != 0:
							if args.min_long_insulin <= insulin <= args.max_long_insulin:
								treatments.append(Insulin(id, timestamp, insulin, True))
							else:
								treatments.append(Insulin(id, timestamp, insulin, False))

					cursor.execute("SELECT _id, timestamp, carbs FROM Treatments")
					for row in cursor.fetchall():
						id, millis_timestamp, carbs = row
						seconds_timestamp = millis_timestamp / 1000.0  
						timestamp = datetime.datetime.fromtimestamp(seconds_timestamp)

						if carbs is not None and carbs != 0:
							meals.append(Meal(id, timestamp, carbs))

					cursor.execute("SELECT _id, timestamp, notes FROM Treatments")
					for row in cursor.fetchall():
						id, millis_timestamp, note = row
						seconds_timestamp = millis_timestamp / 1000.0  
						timestamp = datetime.datetime.fromtimestamp(seconds_timestamp)

						if note is not None and len(note) > 0:
							n = Note(id, timestamp, note)
							notes.append(n)

					measurements.sort()
					print("adjusting treatments...")
					adjust_insulin_treatments(treatments)
					notes.sort()
					meals.sort()
					conn.close()
					os.remove(tmp_file_path)
					return measurements, treatments, meals, notes

def adjust_insulin_treatments(treatments):
	treatments.sort()
	i = 0
	while i < len(treatments) - 1:
		current_treatment = treatments[i]
		next_treatment = treatments[i + 1]
		if isinstance(current_treatment, Insulin) and isinstance(next_treatment, Insulin):
			time_difference = (next_treatment.timestamp - current_treatment.timestamp).total_seconds() / 60.0
			if time_difference <= offset_min_difference:
				current_treatment.timestamp -= datetime.timedelta(minutes=offset_min_difference/2)
				next_treatment.timestamp += datetime.timedelta(minutes=offset_min_difference/2)
		i += 1

if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="xDrip Database Visualizer")
	parser.add_argument("zip_file", help="ZIP file containing the xDrip database (exported from the app)")
	default_days = 7
	default_long_min = 15
	default_long_max = 25
	default_acc_min = 4
	default_acc_max = 10
	parser.add_argument("--last-days", type=int, default=default_days, help=f"Number of last days to create graphs for (default: {default_days})")
	parser.add_argument("--min-long-insulin", type=int, default=default_long_min, help=f"Minimum value for long insulin (default: {default_long_min})")
	parser.add_argument("--max-long-insulin", type=int, default=default_long_max, help=f"Maximum value for long insulin (default: {default_long_max})")
	parser.add_argument("--min-acceptable-bg", type=float, default=default_acc_min, help=f"Minimum acceptable blood sugar value (default: {default_acc_min})")
	parser.add_argument("--max-acceptable-bg", type=float, default=default_acc_max, help=f"Maximum acceptable blood sugar value (default: {default_acc_max})")
	parser.add_argument('--no-widescreen', action='store_true', help="Dont generate widescreen graphs")

	args = parser.parse_args()
	data = load_data(args.zip_file)
	
	create_graphs(data, args.last_days, args.min_acceptable_bg, args.max_acceptable_bg, args.no_widescreen)
