from plotly.subplots import make_subplots
import argparse
import datetime
import io
import numpy as np
import os
import plotly.express as px
import plotly.graph_objs as go
import pprint
import sqlite3
import tempfile
import zipfile

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

# todo draw this to the graph
class Note:
	def __init__(self, id, timestamp, text):
		self.id = id
		self.timestamp = timestamp
		self.text = text


def create_graphs(data, last_days, min_long_insulin, max_long_insulin, min_acceptable_bg, max_acceptable_bg, no_widescreen):
	measurements, treatments, notes = data
	today = datetime.datetime.now().date()
	start_date = today - datetime.timedelta(days=last_days - 1)
	
	measurements = [m for m in measurements if m.timestamp.date() >= start_date]
	treatments = [t for t in treatments if t.timestamp.date() >= start_date]

	# Group measurements by date
	data_by_date = {}
	for measurement in measurements:
		date_str = measurement.timestamp.strftime('%Y-%m-%d')
		if date_str not in data_by_date:
			data_by_date[date_str] = {'timestamps': [], 'values': []}
		data_by_date[date_str]['timestamps'].append(measurement.timestamp)
		data_by_date[date_str]['values'].append(measurement.value)

	# Create an HTML document with graphs
	html_document = """
	<!DOCTYPE html>
	<html>
	<head>
		<title>xDrip Database Visualizer</title>
	</head>
	<body>
	<center>
	<h1>xDrip Database Overview</h1>


	"""
	# Calculate and display averages and deviations
	avg_values = [round(sum(data_by_date[date]['values']) / len(data_by_date[date]['values']), 1) for date in data_by_date]
	avg_bg = round(sum(avg_values) / len(avg_values), 1)

	html_document += f"<h2>Average Blood Glucose: {avg_bg} mmol/l</h2><br><br><br>"

	for date_str in sorted(data_by_date.keys(), reverse=True):  # Sort dates in reverse order
		measurements = data_by_date[date_str]

		# Generate a list of colors based on acceptability
		colors = ['green' if min_acceptable_bg <= val <= max_acceptable_bg else 'red' for val in measurements['values']]

		# Create a trace with markers and lines
		trace = go.Scatter(x=measurements['timestamps'], y=measurements['values'],
							mode='markers+lines', marker={'color': colors}, line={'color': 'gray'}, showlegend=False)

		# Create horizontal lines for acceptable values
		line1 = go.Scatter(x=measurements['timestamps'], y=[min_acceptable_bg] * len(measurements['timestamps']),
						   mode='lines', line={'color': 'red'}, name=f'Acceptable Min: {min_acceptable_bg}', showlegend=False)
		line2 = go.Scatter(x=measurements['timestamps'], y=[max_acceptable_bg] * len(measurements['timestamps']),
						   mode='lines', line={'color': 'red'}, name=f'Acceptable Max: {max_acceptable_bg}', showlegend=False)

		fig = go.Figure(data=[trace, line1, line2])

		for i in range(0, 24, 3):
			line_x = [measurements['timestamps'][0] + datetime.timedelta(hours=i),
					  measurements['timestamps'][0] + datetime.timedelta(hours=i)]
			fig.add_shape(
				go.layout.Shape(
					type='line',
					x0=line_x[0],
					x1=line_x[1],
					y0=0,
					y1=22,
					line=dict(color='lightgrey', width=1),
					xref='x',
					yref='y'
				)
			)

		# Treatments as vertical lines with text annotations
		treatment_values = [t for t in treatments if t.timestamp.strftime('%Y-%m-%d') == date_str]

		offset = 1  # Initial offset
		for i, treatment in enumerate(treatment_values):
			color = 'green' if treatment.is_long_type else 'purple'
			fig.add_shape(go.layout.Shape(
				type='line',
				x0=treatment.timestamp,
				x1=treatment.timestamp,
				y0=0,
				y1=25,
				line=dict(color=color, dash='dash'),
				xref='x',
				yref='y'
			))

			fig.add_annotation(
				text=str(treatment.value),
				x=treatment.timestamp,
				y= 1+ offset,  # Offset the y-coordinate for the text
				showarrow=True,
				font=dict(color=color, size=18, family="Arial")
			)

			# Toggle the offset for the next treatment
			offset *= -1

		# Add barely visible horizontal gridlines
		fig.update_yaxes(showgrid=True, gridcolor="lightgrey", zeroline=False, showline=False, dtick=1)

		fig.update_layout(title_text=f'', xaxis_title='Time', yaxis_title='Blood Glucose (mmol/l)')
		fig.update_xaxes(type='date')

		fig.update_yaxes(range=[0, 22])

		if no_widescreen:
			fig.update_layout(width=1024, height=768)
		else:
			fig.update_layout(width=1600, height=900)

		html_content = fig.to_html(full_html=False, include_plotlyjs='cdn')  # Convert to HTML without plotly.js

		html_document += f"<h2>Date: {date_str}</h2>"
		html_document += html_content


	html_document += """
	</center>
	</body>
	</html>
	"""

	with open('xdrip_database.html', 'w') as html_file:
		html_file.write(html_document)

def load_data(zip_path):
	try:
		# Open the ZIP file and extract the SQLite file to a temporary location
		with zipfile.ZipFile(zip_path, 'r') as archive:
			# Find the SQLite file (assuming there's only one)
			sqlite_file_name = next((file_name for file_name in archive.namelist() if file_name.endswith('.sqlite')), None)

			if sqlite_file_name:
				# Extract the SQLite file to a temporary location
				with archive.open(sqlite_file_name) as sqlite_file:
					with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
						tmp_file.write(sqlite_file.read())
						tmp_file_path = tmp_file.name

					# Create a connection to the SQLite file
					conn = sqlite3.connect(tmp_file_path)
					cursor = conn.cursor()

					measurements = []

					# bg measurements
					cursor.execute("SELECT _id, calculated_value, timestamp FROM BgReadings")
					for row in cursor.fetchall():
						id, value, millis_timestamp = row
						seconds_timestamp = millis_timestamp / 1000.0  # Convert milliseconds to seconds
						timestamp = datetime.datetime.fromtimestamp(seconds_timestamp)
						measurements.append(Measurement(id, round(float(int(value) / 18), 1), timestamp))

					# manual readings
					cursor.execute("SELECT _id, mgdl, timestamp FROM BloodTest")
					for row in cursor.fetchall():
						id, value, millis_timestamp = row
						seconds_timestamp = millis_timestamp / 1000.0  # Convert milliseconds to seconds
						timestamp = datetime.datetime.fromtimestamp(seconds_timestamp)
						manual = Measurement(id, round(float(int(value) / 18), 1), timestamp)
					#	print(f'adding manual: {manual}')
						measurements.append(manual)

					#print('wtf')

					# treatments and notes
					cursor.execute("SELECT _id, timestamp, insulin, notes FROM Treatments")
					treatments = []
					notes = []
				#	custom_parsed_treatments = [] 
					for row in cursor.fetchall():
						id, millis_timestamp, insulin, note_text = row
						seconds_timestamp = millis_timestamp / 1000.0  # Convert milliseconds to seconds
						timestamp = datetime.datetime.fromtimestamp(seconds_timestamp)

						if note_text is not None:
							notes.append(Note(id, timestamp, note_text))

							# try:
							# 	note_int = int(note_text)
							# 	if note_int != 0:
							# 		if args.min_long_insulin <= note_int <= args.max_long_insulin:
							# 			custom_parsed_treatments.append(Insulin(id, timestamp, note_int, True))
							# 		else:
							# 			custom_parsed_treatments.append(Insulin(id, timestamp, note_int, False))
							# except ValueError:
							# 	print("Got one note")
							# 	notes.append(Note(id, timestamp, note_text))

						if insulin is not None and insulin != 0:
							if args.min_long_insulin <= insulin <= args.max_long_insulin:
								treatments.append(Insulin(id, timestamp, insulin, True))
							else:
								treatments.append(Insulin(id, timestamp, insulin, False))


					# i swear to god there was a python bug when i couldnt append to the main treatment list like wtfff ?????
				#	for i in custom_parsed_treatments:
				#		treatments.append(i)

					adjusted_treatments = adjust_insulin_treatments(treatments)
					measurements.sort()

					# Close the database connection and remove the temporary file
					conn.close()
					os.remove(tmp_file_path)

					return measurements, adjusted_treatments, notes

			else:
				print("No SQLite file found in the ZIP archive.")
	except Exception as e:
		print(f"Error: {e}")

def adjust_insulin_treatments(treatments):
	treatments.sort()
	to_return = []
	i = 0
	while i < len(treatments) - 1:
		current_treatment = treatments[i]
		next_treatment = treatments[i + 1]

		# Check if both treatments are insulin treatments
		if isinstance(current_treatment, Insulin) and isinstance(next_treatment, Insulin):
			time_difference = (next_treatment.timestamp - current_treatment.timestamp).total_seconds() / 60.0

			if time_difference <= 10:
				current_treatment.timestamp -= datetime.timedelta(minutes=5)
				next_treatment.timestamp += datetime.timedelta(minutes=5)
				i += 1  # Skip the next treatment as it has been adjusted

		to_return.append(current_treatment)
		i += 1

	# Add the last treatment
	to_return.append(treatments[-1])

	return to_return

	
if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="xDrip Database Visualizer")
	parser.add_argument("zip_file", help="ZIP file containing the xDrip database (exported from the app)")
	parser.add_argument("--last-days", type=int, default=7, help="Number of last days to create graphs for (default: 7)")
	parser.add_argument("--min-long-insulin", type=int, default=15, help="Minimum value for long insulin (default: 15)")
	parser.add_argument("--max-long-insulin", type=int, default=20, help="Maximum value for long insulin (default: 20)")
	parser.add_argument("--min-acceptable-bg", type=float, default=4, help="Minimum acceptable blood sugar value (default: 4)")
	parser.add_argument("--max-acceptable-bg", type=float, default=10, help="Maximum acceptable blood sugar value (default: 10)")
	parser.add_argument('--no-widescreen', action='store_true', help="Dont generate widescreen graphs")

	args = parser.parse_args()
	data = load_data(args.zip_file)

	pp = pprint.PrettyPrinter(indent=4)
#	pp.pprint(data)

	create_graphs(data, args.last_days, args.min_long_insulin, args.max_long_insulin, args.min_acceptable_bg, args.max_acceptable_bg, args.no_widescreen)
