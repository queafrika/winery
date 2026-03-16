import frappe
from frappe.utils import today, add_days, getdate, date_diff


def send_lab_analysis_reminders():
	"""
	Daily job: check for submitted Lab Analysis records where next_analysis_date
	is within the alert window. Send a notification to the assigned analyst and
	auto-create the next pending Lab Analysis.
	"""
	due_records = frappe.get_all(
		"Lab Analysis",
		filters={
			"docstatus": 1,
			"next_analysis_date": ["is", "set"],
			"assigned_analyst": ["is", "set"],
			"alert_sent": 0,
		},
		fields=["name", "next_analysis_date", "assigned_analyst", "alert_before_days",
				"wine_batch", "batch_process_log", "vessel", "test_type"],
	)

	for rec in due_records:
		alert_days = rec.alert_before_days or 1
		alert_trigger_date = add_days(rec.next_analysis_date, -alert_days)

		if getdate(today()) >= getdate(alert_trigger_date):
			_notify_analyst(rec)
			_create_next_analysis(rec)
			frappe.db.set_value("Lab Analysis", rec.name, "alert_sent", 1)

	frappe.db.commit()


def _notify_analyst(rec):
	days_left = (getdate(rec.next_analysis_date) - getdate(today())).days

	if days_left < 0:
		message = f"Lab analysis for Wine Batch {rec.wine_batch or ''} is OVERDUE by {abs(days_left)} day(s). Please perform the {rec.test_type or 'analysis'} immediately."
	elif days_left == 0:
		message = f"Lab analysis for Wine Batch {rec.wine_batch or ''} is due TODAY. Please perform the {rec.test_type or 'analysis'}."
	else:
		message = f"Reminder: Lab analysis for Wine Batch {rec.wine_batch or ''} is due in {days_left} day(s) on {rec.next_analysis_date}. Test type: {rec.test_type or 'N/A'}."

	frappe.publish_realtime(
		"eval_js",
		f"frappe.show_alert({{message: {frappe.as_json(message)}, indicator: 'orange'}}, 10);",
		user=rec.assigned_analyst,
	)

	frappe.get_doc({
		"doctype": "Notification Log",
		"subject": f"Lab Analysis Due — {rec.wine_batch or rec.name}",
		"email_content": message,
		"for_user": rec.assigned_analyst,
		"type": "Alert",
		"document_type": "Lab Analysis",
		"document_name": rec.name,
	}).insert(ignore_permissions=True)


def _create_next_analysis(rec):
	"""Auto-create a new pending Lab Analysis for the next cycle."""
	already_exists = frappe.db.exists("Lab Analysis", {
		"wine_batch": rec.wine_batch,
		"test_type": rec.test_type,
		"docstatus": 0,
		"analysis_date": [">=", rec.next_analysis_date],
	})
	if already_exists:
		return

	new_doc = frappe.new_doc("Lab Analysis")
	new_doc.wine_batch = rec.wine_batch
	new_doc.batch_process_log = rec.batch_process_log
	new_doc.vessel = rec.vessel
	new_doc.test_type = rec.test_type
	new_doc.analysis_date = frappe.utils.now()
	new_doc.analyzed_by = rec.assigned_analyst
	new_doc.assigned_analyst = rec.assigned_analyst
	new_doc.alert_before_days = rec.alert_before_days
	new_doc.status = "Pending"
	new_doc.insert(ignore_permissions=True)


# ─────────────────────────────────────────────────────────────────────────────
#  Ripening Alerts
# ─────────────────────────────────────────────────────────────────────────────
OVERDUE_THRESHOLD_DAYS = 7


def send_ripening_ready_reminders():
	"""
	Daily job: find Ripening Batches whose expected_end_date is TOMORROW.
	Send a 24-hour heads-up to Winery Managers so they can prepare.
	"""
	tomorrow = add_days(today(), 1)

	batches_due_tomorrow = frappe.get_all(
		"Ripening Batch",
		filters={
			"docstatus": 1,
			"actual_end_date": ["is", "not set"],
			"expected_end_date": getdate(tomorrow),
		},
		fields=["name", "rack", "start_date", "expected_end_date",
				"ripening_days", "total_fingers_ripening", "banana_item"],
	)

	if not batches_due_tomorrow:
		return

	recipients = _get_winery_alert_recipients()

	for rb in batches_due_tomorrow:
		days_ripening = date_diff(tomorrow, rb.start_date) if rb.start_date else 0
		_send_ripening_ready_alert(rb, days_ripening, recipients)

	frappe.db.commit()


def _send_ripening_ready_alert(rb, days_ripening, recipients):
	subject = f"✅ Ripening Batch Ready Tomorrow — {rb.name}"

	body = f"""
<h3>Ripening Batch Ready for Transfer</h3>
<p>The following ripening batch is expected to be ready <b>tomorrow ({rb.expected_end_date})</b>.</p>
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;">
  <tr><td><b>Ripening Batch</b></td><td>{rb.name}</td></tr>
  <tr><td><b>Ripening Rack</b></td><td>{rb.rack}</td></tr>
  <tr><td><b>Banana Item</b></td><td>{rb.banana_item}</td></tr>
  <tr><td><b>Start Date</b></td><td>{rb.start_date}</td></tr>
  <tr><td><b>Expected End Date</b></td><td><b>{rb.expected_end_date}</b></td></tr>
  <tr><td><b>Days in Ripening</b></td><td>{days_ripening} days</td></tr>
  <tr><td><b>Total Fingers</b></td><td>{rb.total_fingers_ripening}</td></tr>
</table>
<br>
<p style="color:green;"><b>Action:</b> Please prepare the destination warehouse and
schedule staff for the End Ripening transfer tomorrow.</p>
<p><a href="/app/ripening-batch/{rb.name}">View Ripening Batch →</a></p>
"""

	for user_email in recipients:
		frappe.get_doc({
			"doctype": "Notification Log",
			"subject": subject,
			"email_content": body,
			"for_user": user_email,
			"type": "Alert",
			"document_type": "Ripening Batch",
			"document_name": rb.name,
		}).insert(ignore_permissions=True)

		frappe.sendmail(
			recipients=[user_email],
			subject=subject,
			message=body,
			now=True,
		)

		frappe.publish_realtime(
			"eval_js",
			f"frappe.show_alert({{message: 'Ripening Batch {rb.name} is ready for transfer tomorrow!', indicator: 'green'}}, 15);",
			user=user_email,
		)


def check_overdue_ripening_batches():
	"""
	Daily job: find all active Ripening Batches where expected_end_date has
	passed OR bananas have been ripening for more than OVERDUE_THRESHOLD_DAYS.
	Send an email + in-app alert to the batch owner and all Winery Manager users.
	"""
	active_batches = frappe.get_all(
		"Ripening Batch",
		filters={
			"docstatus": 1,
			"actual_end_date": ["is", "not set"],
		},
		fields=["name", "rack", "start_date", "expected_end_date",
				"ripening_days", "total_fingers_ripening", "owner"],
	)

	if not active_batches:
		return

	recipients = _get_winery_alert_recipients()

	for rb in active_batches:
		days_ripening = date_diff(today(), rb.start_date) if rb.start_date else 0
		is_overdue_by_days = days_ripening > OVERDUE_THRESHOLD_DAYS
		is_past_expected = (
			rb.expected_end_date and getdate(today()) > getdate(rb.expected_end_date)
		)

		if not (is_overdue_by_days or is_past_expected):
			continue

		days_over = days_ripening - (rb.ripening_days or OVERDUE_THRESHOLD_DAYS)
		_send_ripening_overdue_alert(rb, days_ripening, days_over, recipients)

	frappe.db.commit()


def _send_ripening_overdue_alert(rb, days_ripening, days_over, recipients):
	subject = f"⚠️ Overdue Ripening Batch — {rb.name} ({days_ripening} days)"

	body = f"""
<h3>Ripening Batch Overdue Alert</h3>
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;">
  <tr><td><b>Ripening Batch</b></td><td>{rb.name}</td></tr>
  <tr><td><b>Ripening Rack</b></td><td>{rb.rack}</td></tr>
  <tr><td><b>Start Date</b></td><td>{rb.start_date}</td></tr>
  <tr><td><b>Expected End Date</b></td><td>{rb.expected_end_date or "Not set"}</td></tr>
  <tr><td><b>Days in Ripening</b></td><td>{days_ripening} days</td></tr>
  <tr><td><b>Days Overdue</b></td><td style="color:red;"><b>{days_over} day(s) past target</b></td></tr>
  <tr><td><b>Total Fingers</b></td><td>{rb.total_fingers_ripening}</td></tr>
</table>
<br>
<p style="color:red;"><b>Action Required:</b> Please inspect the ripening batch immediately.
Bananas left too long may over-ripen and affect wine quality.</p>
<p><a href="/app/ripening-batch/{rb.name}">View Ripening Batch →</a></p>
"""

	for user_email in recipients:
		# In-app notification
		frappe.get_doc({
			"doctype": "Notification Log",
			"subject": subject,
			"email_content": body,
			"for_user": user_email,
			"type": "Alert",
			"document_type": "Ripening Batch",
			"document_name": rb.name,
		}).insert(ignore_permissions=True)

		# Email
		frappe.sendmail(
			recipients=[user_email],
			subject=subject,
			message=body,
			now=True,
		)

		# Real-time desk alert
		frappe.publish_realtime(
			"eval_js",
			f"frappe.show_alert({{message: 'Ripening Batch {rb.name} is overdue by {days_over} days!', indicator: 'red'}}, 15);",
			user=user_email,
		)


def _get_winery_alert_recipients():
	"""Return list of user emails: batch owners + users with Winery Manager role."""
	emails = set()

	# Users with Winery Manager role
	managers = frappe.get_all(
		"Has Role",
		filters={"role": "Winery Manager", "parenttype": "User"},
		fields=["parent"],
	)
	for m in managers:
		email = frappe.db.get_value("User", m.parent, "email")
		if email:
			emails.add(email)

	# Fallback: system default email or Administrator
	if not emails:
		system_email = frappe.db.get_single_value("Email Account", "email_id") or "Administrator"
		emails.add(system_email)

	return list(emails)


# ─────────────────────────────────────────────────────────────────────────────
#  Ripening Rack Daily Usage Report
# ─────────────────────────────────────────────────────────────────────────────

def send_ripening_rack_report():
	"""Daily job: email all Winery Managers a rack usage summary."""
	racks = frappe.get_all(
		"Ripening Rack",
		fields=["name", "rack_number", "warehouse", "capacity_fingers", "status"],
		order_by="rack_number asc",
	)

	if not racks:
		return

	rack_rows = []
	for rack in racks:
		fingers_in_use = 0
		if rack.warehouse:
			result = frappe.db.sql("""
				SELECT COALESCE(SUM(actual_qty), 0) AS qty
				FROM `tabStock Ledger Entry`
				WHERE warehouse = %s AND is_cancelled = 0
			""", rack.warehouse, as_dict=True)
			fingers_in_use = int(result[0].qty or 0)

		capacity = rack.capacity_fingers or 0
		pct = round((fingers_in_use / capacity) * 100, 1) if capacity > 0 else 0
		remaining = max(0, capacity - fingers_in_use)

		# Active ripening batches on this rack
		active_batches = frappe.get_all(
			"Ripening Batch",
			filters={"rack": rack.name, "docstatus": 1, "actual_end_date": ["is", "not set"]},
			fields=["name", "start_date", "expected_end_date", "total_fingers_ripening"],
		)

		rack_rows.append({
			"rack": rack,
			"fingers_in_use": fingers_in_use,
			"capacity": capacity,
			"pct": pct,
			"remaining": remaining,
			"active_batches": active_batches,
		})

	# Sort: critical first, then by usage desc
	rack_rows.sort(key=lambda x: -x["pct"])

	_send_rack_report_email(rack_rows)
	frappe.db.commit()


def _send_rack_report_email(rack_rows):
	from frappe.utils import today as _today

	subject = f"Ripening Rack Status Report — {_today()}"

	# Build rack table rows
	table_rows = ""
	for r in rack_rows:
		pct = r["pct"]
		if pct >= 90:
			color = "#e74c3c"
			badge = '<span style="background:#e74c3c;color:#fff;padding:2px 8px;border-radius:10px;font-size:11px;">Critical</span>'
		elif pct >= 70:
			color = "#e67e22"
			badge = '<span style="background:#e67e22;color:#fff;padding:2px 8px;border-radius:10px;font-size:11px;">High</span>'
		elif pct > 0:
			color = "#27ae60"
			badge = '<span style="background:#27ae60;color:#fff;padding:2px 8px;border-radius:10px;font-size:11px;">Normal</span>'
		else:
			color = "#bdc3c7"
			badge = '<span style="background:#bdc3c7;color:#fff;padding:2px 8px;border-radius:10px;font-size:11px;">Empty</span>'

		# Mini progress bar (20 chars wide using filled/empty blocks)
		filled = int(pct / 5)
		bar = f'<div style="background:#e9ecef;border-radius:4px;height:14px;width:160px;overflow:hidden;display:inline-block;vertical-align:middle;"><div style="width:{pct}%;height:100%;background:{color};"></div></div>'

		# Active batches list
		batch_list = ""
		for b in r["active_batches"]:
			days_in = date_diff(today(), b.start_date) if b.start_date else 0
			batch_list += f"<br>&nbsp;&nbsp;↳ {b.name} ({days_in}d, exp: {b.expected_end_date or '—'})"

		table_rows += f"""
		<tr style="border-bottom:1px solid #eee;">
			<td style="padding:8px;font-weight:600;">{r['rack'].rack_number}</td>
			<td style="padding:8px;">{bar} &nbsp;{pct}%</td>
			<td style="padding:8px;">{r['fingers_in_use']:,}</td>
			<td style="padding:8px;">{r['capacity']:,}</td>
			<td style="padding:8px;">{r['remaining']:,}</td>
			<td style="padding:8px;">{badge}</td>
			<td style="padding:8px;font-size:12px;color:#555;">{r['rack'].status}{batch_list}</td>
		</tr>"""

	total_capacity = sum(r["capacity"] for r in rack_rows)
	total_in_use = sum(r["fingers_in_use"] for r in rack_rows)
	total_pct = round((total_in_use / total_capacity) * 100, 1) if total_capacity > 0 else 0
	critical_count = sum(1 for r in rack_rows if r["pct"] >= 90)

	body = f"""
<div style="font-family:Arial,sans-serif;max-width:800px;">
  <h2 style="color:#2c3e50;border-bottom:2px solid #3498db;padding-bottom:8px;">
    🍌 Ripening Rack Status Report
  </h2>
  <p style="color:#666;">Generated: <b>{_today()}</b></p>

  {"<p style='background:#ffeaa7;padding:10px;border-radius:4px;border-left:4px solid #e74c3c;'><b>⚠️ " + str(critical_count) + " rack(s) at critical capacity (≥90%)!</b></p>" if critical_count else ""}

  <table style="width:100%;border-collapse:collapse;margin-top:16px;">
    <thead>
      <tr style="background:#3498db;color:#fff;">
        <th style="padding:10px;text-align:left;">Rack</th>
        <th style="padding:10px;text-align:left;">Usage</th>
        <th style="padding:10px;text-align:left;">In Use</th>
        <th style="padding:10px;text-align:left;">Capacity</th>
        <th style="padding:10px;text-align:left;">Available</th>
        <th style="padding:10px;text-align:left;">Status</th>
        <th style="padding:10px;text-align:left;">Batches</th>
      </tr>
    </thead>
    <tbody>
      {table_rows}
    </tbody>
    <tfoot>
      <tr style="background:#ecf0f1;font-weight:600;">
        <td style="padding:8px;">TOTAL</td>
        <td style="padding:8px;">{total_pct}%</td>
        <td style="padding:8px;">{total_in_use:,}</td>
        <td style="padding:8px;">{total_capacity:,}</td>
        <td style="padding:8px;">{max(0, total_capacity - total_in_use):,}</td>
        <td colspan="2"></td>
      </tr>
    </tfoot>
  </table>

  <p style="margin-top:20px;font-size:12px;color:#999;">
    This report is sent daily. To view live rack status, visit the
    <a href="/app/ripening-rack">Ripening Rack list</a>.
  </p>
</div>
"""

	recipients = _get_winery_alert_recipients()
	for email in recipients:
		try:
			frappe.sendmail(
				recipients=[email],
				subject=subject,
				message=body,
				now=True,
			)
		except Exception:
			pass  # Email not configured yet — in-app notification still created
		frappe.get_doc({
			"doctype": "Notification Log",
			"subject": subject,
			"email_content": body,
			"for_user": email,
			"type": "Alert",
		}).insert(ignore_permissions=True)
