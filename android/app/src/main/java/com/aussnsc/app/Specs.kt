package com.aussnsc.app

import org.json.JSONArray
import org.json.JSONObject
import java.net.URLEncoder
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale
import java.util.TimeZone

fun enc(s: String): String = URLEncoder.encode(s, "UTF-8")

fun cap(s: String): String = s.replaceFirstChar { it.uppercase() }

private fun hm(s: String): String = s.take(5)

private val DAYS = listOf("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")

private fun bdFormat(): SimpleDateFormat {
    val f = SimpleDateFormat("yyyy-MM-dd", Locale.US)
    f.timeZone = TimeZone.getTimeZone("Asia/Dhaka")
    return f
}

fun todayBd(): String = bdFormat().format(Date())

fun shiftDay(day: String, delta: Int): String {
    val f = bdFormat()
    val c = Calendar.getInstance(TimeZone.getTimeZone("Asia/Dhaka"))
    c.time = f.parse(day) ?: Date()
    c.add(Calendar.DAY_OF_MONTH, delta)
    return f.format(c.time)
}

// ───────────── list pages ─────────────

data class Entry(
    val title: String,
    val subtitle: String = "",
    val body: String = "",
    val badge: String = "",
    val route: String? = null,
    val url: String? = null,
    val data: JSONObject? = null,
)

typealias Act = Pair<String, suspend () -> Unit>

fun act(label: String, f: suspend () -> Unit): Act = Pair(label, f)

class ListSpec(
    val title: String,
    val section: String,
    val description: String,
    val needsLogin: Boolean = false,
    val searchable: Boolean = false,
    val actionLabel: String? = null,
    val actionRoute: String? = null,
    val empty: String = "Nothing here yet.",
    val path: suspend (arg: String, q: String) -> String,
    val map: (Any?) -> List<Entry>,
    val actions: ((Entry) -> List<Act>)? = null,
)

private fun rows(v: Any?, f: (JSONObject) -> Entry): List<Entry> =
    (v as? JSONArray)?.objects()?.map(f) ?: emptyList()

private fun join(vararg parts: String): String = parts.filter { it.isNotBlank() }.joinToString(" · ")

private suspend fun myClassId(): Int = Api.obj("GET", "/me/student").getInt("class_id")

private fun bullets(x: Any?): String = when (x) {
    is JSONArray -> (0 until x.length()).joinToString("\n") { "• " + x.opt(it).toString() }
    is JSONObject -> x.keys().asSequence().joinToString("\n") { k -> "${cap(k)}: ${x.opt(k)}" }
    null -> ""
    else -> x.toString()
}

private fun contentRows(v: Any?): List<Entry> {
    val o = v as? JSONObject ?: return emptyList()
    return o.keys().asSequence()
        .map { k -> Entry(cap(k.replace('_', ' ')), body = bullets(o.opt(k))) }
        .filter { it.body.isNotBlank() }
        .toList()
}

private fun entryId(e: Entry): Int = e.data?.optInt("id") ?: 0

val specs: Map<String, ListSpec> = mapOf(
    "notices" to ListSpec(
        title = "Notices", section = "Public", description = "Official school announcements.",
        searchable = true, empty = "No notices yet.",
        path = { _, q -> if (q.isBlank()) "/notices?limit=50" else "/notices?limit=50&q=" + enc(q) },
        map = { v ->
            rows(v) { n ->
                Entry(
                    n.str("title"),
                    join(cap(n.str("category")), n.str("created_at").take(10), if (n.optBoolean("pinned")) "Pinned" else ""),
                    body = n.str("body"), data = n,
                )
            }
        },
        actions = { e -> if (Session.role == "admin") listOf(act("Delete notice") { Api.request("DELETE", "/admin/notices/${entryId(e)}") }) else emptyList() },
    ),
    "results_my" to ListSpec(
        title = "My Results", section = "Academics", description = "Published results on your record.",
        needsLogin = true, empty = "No published results yet.",
        path = { arg, _ -> if (arg.isBlank()) "/me/results" else "/students/$arg/results" },
        map = { v ->
            rows(v) { r ->
                Entry(
                    "${r.str("exam")} ${r.optInt("exam_year")}",
                    join("GPA " + r.str("gpa", "-"), "Grade " + r.str("grade", "-"), cap(r.str("status"))),
                    body = r.list("subjects").joinToString("\n") { it.str("subject") + ": " + it.str("marks", "-") },
                )
            }
        },
    ),
    "attendance" to ListSpec(
        title = "Attendance", section = "Academics", description = "Your attendance record.",
        needsLogin = true,
        path = { arg, _ -> if (arg.isBlank()) "/me/attendance" else "/students/$arg/attendance" },
        map = { v ->
            val o = v as? JSONObject ?: JSONObject()
            val head = Entry(
                "Attendance rate: ${o.str("rate_percent", "0")}%",
                "Present ${o.optInt("present")} · Absent ${o.optInt("absent")} · Late ${o.optInt("late")} · ${o.optInt("total_days")} days recorded",
            )
            listOf(head) + o.list("records").map { Entry(it.str("day"), cap(it.str("status"))) }
        },
    ),
    "routine_classes" to ListSpec(
        title = "Class Routine", section = "Academics", description = "Choose a class to see its weekly timetable.",
        path = { _, _ -> "/classes" },
        map = { v -> rows(v) { c -> Entry(c.str("label"), route = "list/routine?arg=${c.optInt("id")}") } },
    ),
    "routine" to ListSpec(
        title = "Class Routine", section = "Academics", description = "Weekly class timetable.",
        empty = "No routine has been published for this class yet.",
        path = { arg, _ -> if (arg == "me") "/routines/class/${myClassId()}" else "/routines/class/$arg" },
        map = { v ->
            rows(v) { s ->
                val end = s.str("end_time")
                val time = hm(s.str("start_time")) + (if (end.isBlank()) "" else "-" + hm(end))
                Entry(
                    (DAYS.getOrNull(s.optInt("weekday")) ?: "") + " · " + s.str("subject"),
                    join(time, s.str("teacher_name"), s.str("room")),
                )
            }
        },
    ),
    "exam_routine" to ListSpec(
        title = "Exam Routine", section = "Academics", description = "Upcoming examination schedule.",
        empty = "No upcoming exams are scheduled.",
        path = { arg, _ ->
            when {
                arg == "me" -> "/routines/exam?class_id=${myClassId()}"
                arg.isBlank() -> "/routines/exam"
                else -> "/routines/exam?class_id=$arg"
            }
        },
        map = { v ->
            rows(v) { s ->
                val mins = s.optInt("duration_minutes")
                Entry(
                    s.str("subject"),
                    join(s.str("exam"), s.str("day"), hm(s.str("start_time")), if (mins > 0) "$mins min" else "", s.str("room")),
                )
            }
        },
    ),
    "assignments" to ListSpec(
        title = "Assignments", section = "Academics", description = "Homework and class tasks.",
        needsLogin = true, empty = "No assignments yet.",
        path = { arg, _ -> if (arg.isBlank()) "/assignments?limit=50" else "/assignments?student_id=$arg&limit=50" },
        map = { v ->
            rows(v) { a ->
                val role = Session.role
                val st = a.str("my_submission_status")
                val id = a.optInt("id")
                Entry(
                    a.str("title"),
                    join(a.str("subject"), a.str("class_label"), if (a.str("due_date").isBlank()) "" else "Due " + a.str("due_date")),
                    body = a.str("instructions"),
                    badge = if (role == "student") (if (st.isBlank()) "Not submitted" else cap(st)) else "",
                    route = when (role) {
                        "student" -> "form/submit_assignment?arg=$id"
                        "teacher", "admin" -> "list/submissions?arg=$id"
                        else -> null
                    },
                )
            }
        },
    ),
    "submissions" to ListSpec(
        title = "Submissions", section = "Teacher", description = "Tap a submission to give feedback.",
        needsLogin = true, empty = "No submissions yet.",
        path = { arg, _ -> "/assignments/$arg/submissions" },
        map = { v ->
            rows(v) { s ->
                Entry(
                    s.str("student_name"), join(cap(s.str("status")), s.str("grade"), s.str("submitted_at").take(10)),
                    body = join(s.str("text"), if (s.str("file_url").isBlank()) "" else "Attachment: " + Api.fileUrl(s.str("file_url"))),
                    route = "form/review?arg=${s.optInt("id")}",
                )
            }
        },
    ),
    "materials" to ListSpec(
        title = "Study Materials", section = "Academics", description = "Learning resources shared by teachers.",
        needsLogin = true, empty = "No materials yet.",
        path = { _, _ -> "/materials?limit=100" },
        map = { v ->
            rows(v) { m ->
                val file = m.str("file_url")
                val link = m.str("link")
                Entry(
                    m.str("title"), join(cap(m.str("kind")), m.str("subject")),
                    url = if (file.isNotBlank()) Api.fileUrl(file) else if (link.isNotBlank()) link else null,
                    data = m,
                )
            }
        },
        actions = { e -> if (Session.role == "teacher" || Session.role == "admin") listOf(act("Delete material") { Api.request("DELETE", "/materials/${entryId(e)}") }) else emptyList() },
    ),
    "calendar" to ListSpec(
        title = "Academic Calendar", section = "Academics", description = "Important dates and school events.",
        empty = "No events yet.",
        path = { _, _ -> "/calendar" },
        map = { v ->
            rows(v) { e ->
                val end = e.str("end_date")
                Entry(e.str("title"), join(e.str("start_date") + (if (end.isBlank()) "" else " to $end"), cap(e.str("kind"))), body = e.str("description"))
            }
        },
    ),
    "gallery" to ListSpec(
        title = "Gallery", section = "School", description = "Photos from school activities and events.",
        empty = "No albums yet.",
        path = { _, _ -> "/gallery/albums" },
        map = { v -> rows(v) { a -> Entry(a.str("title"), "${a.optInt("photo_count")} photos", body = a.str("description"), route = "album/${a.optInt("id")}") } },
    ),
    "teachers" to ListSpec(
        title = "Teacher Directory", section = "School", description = "Find teaching staff and departments.",
        searchable = true, empty = "No teachers found.",
        path = { _, q -> if (q.isBlank()) "/teachers" else "/teachers?q=" + enc(q) },
        map = { v ->
            rows(v) { t ->
                Entry(t.str("full_name"), join(t.str("designation"), t.str("department")), body = join(t.str("phone"), t.str("email")))
            }
        },
    ),
    "admission" to ListSpec(
        title = "Admission", section = "Public", description = "Admission information and application guidance.",
        actionLabel = "Apply for admission", actionRoute = "form/admission",
        empty = "Admission details haven't been published yet. You can still send an application below.",
        path = { _, _ -> "/content/admission" },
        map = { v -> contentRows(v) },
    ),
    "about" to ListSpec(
        title = "About School", section = "School", description = "Ahammad Uddin Shah Shishu Niketan School & College.",
        empty = "The school hasn't published this page yet.",
        path = { _, _ -> "/content/about" },
        map = { v -> contentRows(v) },
    ),
    "channels" to ListSpec(
        title = "Class Channels", section = "Community", description = "Channels for your class and school.",
        needsLogin = true, empty = "No channels available for your account yet.",
        path = { _, _ -> "/channels" },
        map = { v ->
            rows(v) { c ->
                Entry("# " + c.str("name"), join(c.str("class_label", "School-wide"), if (c.optBoolean("announcement_only")) "Announcements only" else "", c.str("description")), route = "chat/${c.optInt("id")}")
            }
        },
    ),
    "my_classes" to ListSpec(
        title = "My Classes", section = "Teacher", description = "Classes assigned to you.",
        needsLogin = true, empty = "No classes are assigned to you yet. Ask the school admin.",
        path = { _, _ -> "/teacher/classes" },
        map = { v -> rows(v) { c -> Entry(c.str("class_label"), c.str("subject"), route = "list/roster?arg=${c.optInt("class_id")}") } },
    ),
    "roster" to ListSpec(
        title = "Class Roster", section = "Teacher", description = "Students in this class.",
        needsLogin = true, empty = "No students in this class.",
        path = { arg, _ -> "/classes/$arg/students" },
        map = { v -> rows(v) { s -> Entry("${s.optInt("roll")}. ${s.str("full_name")}", s.str("class_label")) } },
    ),
    "children" to ListSpec(
        title = "My Children", section = "Parent", description = "Children linked to your account.",
        needsLogin = true, actionLabel = "Link another child", actionRoute = "list/my_links",
        empty = "No linked children yet. Send a link request first.",
        path = { _, _ -> "/parent/children" },
        map = { v -> rows(v) { s -> Entry(s.str("full_name"), join(s.str("class_label"), "Roll " + s.optInt("roll")), route = "child/${s.optInt("id")}") } },
    ),
    "my_links" to ListSpec(
        title = "Child Link Requests", section = "Parent", description = "Parent-child access needs school verification.",
        needsLogin = true, actionLabel = "Link a child", actionRoute = "form/child_link",
        empty = "You haven't sent any requests.",
        path = { _, _ -> "/parent/links" },
        map = { v ->
            rows(v) { l ->
                Entry(l.str("claimed_name"), join(l.str("claimed_class"), "Roll " + l.optInt("claimed_roll")), body = "Relationship: " + l.str("relationship"), badge = cap(l.str("status")))
            }
        },
    ),
    "moderation" to ListSpec(
        title = "Community Moderation", section = "Teacher", description = "Messages reported in your channels. Tap one to act.",
        needsLogin = true, empty = "No open reports.",
        path = { _, _ -> "/moderation/reports" },
        map = { v -> rows(v) { r -> Entry(r.str("message_body"), "Reason: " + r.str("reason"), data = r) } },
        actions = { e ->
            listOf(
                act("Resolve report") { Api.request("POST", "/moderation/reports/${entryId(e)}/resolve") },
                act("Delete message") {
                    Api.request("DELETE", "/messages/${e.data?.optInt("message_id") ?: 0}")
                    Api.request("POST", "/moderation/reports/${entryId(e)}/resolve")
                },
            )
        },
    ),
    "admin_stats" to ListSpec(
        title = "Dashboard", section = "Administration", description = "School overview.",
        needsLogin = true,
        path = { _, _ -> "/admin/stats" },
        map = { v ->
            val o = v as? JSONObject ?: JSONObject()
            val roles = o.optJSONObject("users_by_role")
            val rate = if (o.isNull("today_attendance_rate")) "none marked yet" else o.str("today_attendance_rate") + "% present"
            val rolesText = if (roles == null) "" else roles.keys().asSequence().joinToString(" · ") { k -> k + " " + roles.optInt(k) }
            listOf(
                Entry("Students", o.str("students")),
                Entry("Teachers", o.str("teachers")),
                Entry("Pending parent links", o.str("pending_parent_links"), route = "list/admin_links"),
                Entry("New admission applications", o.str("new_admission_applications"), route = "list/admin_apps"),
                Entry("Open message reports", o.str("open_message_reports"), route = "list/moderation"),
                Entry("Today's attendance", rate),
                Entry("Accounts by role", rolesText, route = "list/admin_users"),
            )
        },
    ),
    "admin_links" to ListSpec(
        title = "Parent Link Requests", section = "Administration", description = "Tap a request to approve or reject it.",
        needsLogin = true, empty = "No pending requests.",
        path = { _, _ -> "/admin/parent-links?status=pending" },
        map = { v ->
            rows(v) { l ->
                Entry(
                    l.str("parent_name") + " -> " + l.str("claimed_name"),
                    join(l.str("claimed_class"), "Roll " + l.optInt("claimed_roll"), l.str("relationship")),
                    body = if (l.isNull("student_id")) "No automatic match found. Approve it from /docs with a student_id." else "Matched student: " + l.str("student_name"),
                    data = l,
                )
            }
        },
        actions = { e ->
            val id = entryId(e)
            listOf(
                act("Approve") { Api.request("POST", "/admin/parent-links/$id/decision", JSONObject().put("approve", true)) },
                act("Reject") { Api.request("POST", "/admin/parent-links/$id/decision", JSONObject().put("approve", false)) },
            )
        },
    ),
    "admin_users" to ListSpec(
        title = "Users", section = "Administration", description = "Tap a user to change their role or disable the account.",
        needsLogin = true, searchable = true, empty = "No users found.",
        path = { arg, q ->
            "/admin/users?limit=100" + (if (arg.isBlank()) "" else "&role=$arg") + (if (q.isBlank()) "" else "&q=" + enc(q))
        },
        map = { v ->
            rows(v) { u ->
                Entry(
                    u.str("full_name"), join(cap(u.str("role")), u.str("phone"), u.str("email")),
                    badge = if (u.optBoolean("is_active", true)) "" else "Disabled", data = u,
                )
            }
        },
        actions = { e ->
            val id = entryId(e)
            val current = e.data?.str("role") ?: ""
            val active = e.data?.optBoolean("is_active", true) ?: true
            val roleActs = listOf("student", "parent", "teacher", "admin", "public").filter { it != current }
                .map { r -> act("Make " + r) { Api.request("PATCH", "/admin/users/$id", JSONObject().put("role", r)) } }
            roleActs + act(if (active) "Disable account" else "Enable account") {
                Api.request("PATCH", "/admin/users/$id", JSONObject().put("is_active", !active))
            }
        },
    ),
    "admin_apps" to ListSpec(
        title = "Admission Applications", section = "Administration", description = "Tap an application to update its status.",
        needsLogin = true, empty = "No applications.",
        path = { _, _ -> "/admin/admission/applications" },
        map = { v ->
            rows(v) { a ->
                Entry(
                    a.str("applicant_name"), join(a.str("class_applying"), a.str("phone"), a.str("email")),
                    body = join("Guardian: " + a.str("guardian_name"), a.str("message")), badge = cap(a.str("status")), data = a,
                )
            }
        },
        actions = { e ->
            val id = entryId(e)
            listOf("contacted", "accepted", "rejected").map { s ->
                act("Mark " + s) { Api.request("PATCH", "/admin/admission/applications/$id", JSONObject().put("status", s)) }
            }
        },
    ),
)

// ───────────── form pages ─────────────

enum class Kind { Text, Multiline, Password, Number, Choice }

class Field(
    val key: String,
    val label: String,
    val kind: Kind = Kind.Text,
    val required: Boolean = true,
    val choices: (suspend () -> List<Pair<String, String>>)? = null,
)

class FormSpec(
    val title: String,
    val intro: String,
    val submitLabel: String,
    val needsLogin: Boolean = true,
    val fields: List<Field>,
    val submit: suspend (values: Map<String, String>, arg: String) -> String,
)

/** Non-blank values as JSON; keys listed in `ints` are sent as numbers. */
private fun body(v: Map<String, String>, vararg ints: String): JSONObject {
    val o = JSONObject()
    for ((k, value) in v) {
        if (value.isBlank()) continue
        if (k in ints) o.put(k, value.trim().toIntOrNull() ?: 0) else o.put(k, value)
    }
    return o
}

val forms: Map<String, FormSpec> = mapOf(
    "admission" to FormSpec(
        title = "Admission application", intro = "Tell us about the student. The school office will contact you.",
        submitLabel = "Send application", needsLogin = false,
        fields = listOf(
            Field("applicant_name", "Student's full name"),
            Field("guardian_name", "Guardian's name"),
            Field("phone", "Phone number (e.g. 017xxxxxxxx)", Kind.Number),
            Field("email", "Email (optional)", required = false),
            Field("class_applying", "Class applying for"),
            Field("previous_school", "Previous school (optional)", required = false),
            Field("message", "Message (optional)", Kind.Multiline, required = false),
        ),
        submit = { v, _ ->
            Api.request("POST", "/admission/applications", body(v), false)
            "Application sent. The school office will contact you."
        },
    ),
    "child_link" to FormSpec(
        title = "Link a child", intro = "Enter your child's details exactly as the school has them. An admin will verify the request.",
        submitLabel = "Send verification request",
        fields = listOf(
            Field("student_name", "Student's full name"),
            Field("class_name", "Class (e.g. 10)"),
            Field("roll", "Roll number", Kind.Number),
            Field("relationship", "Your relationship (Father, Mother, Guardian)"),
        ),
        submit = { v, _ ->
            Api.request("POST", "/parent/links", body(v, "roll"))
            "Request sent. You'll get access once the school approves it."
        },
    ),
    "create_assignment" to FormSpec(
        title = "Create assignment", intro = "Prepare homework for one of your classes.", submitLabel = "Publish assignment",
        fields = listOf(
            Field("class_id", "Class", Kind.Choice, choices = {
                Api.arr("/teacher/classes").objects().map { it.optInt("class_id").toString() to join(it.str("class_label"), it.str("subject")) }
            }),
            Field("title", "Title"),
            Field("instructions", "Instructions", Kind.Multiline, required = false),
            Field("subject", "Subject (optional)", required = false),
            Field("due_date", "Due date YYYY-MM-DD (optional)", required = false),
        ),
        submit = { v, _ ->
            Api.request("POST", "/assignments", body(v, "class_id"))
            "Assignment published."
        },
    ),
    "submit_assignment" to FormSpec(
        title = "Submit assignment", intro = "Write your answer below. You can resubmit until your teacher reviews it.",
        submitLabel = "Submit",
        fields = listOf(Field("text", "Your answer", Kind.Multiline)),
        submit = { v, arg ->
            Api.request("POST", "/assignments/$arg/submissions", body(v))
            "Submitted. Your teacher will review it."
        },
    ),
    "review" to FormSpec(
        title = "Review submission", intro = "Give the student feedback and an optional grade.", submitLabel = "Save review",
        fields = listOf(Field("feedback", "Feedback", Kind.Multiline, required = false), Field("grade", "Grade (optional)", required = false)),
        submit = { v, arg ->
            Api.request("PATCH", "/submissions/$arg/review", body(v))
            "Review saved."
        },
    ),
    "notice" to FormSpec(
        title = "Post a notice", intro = "Published immediately on the Notices page.", submitLabel = "Publish notice",
        fields = listOf(
            Field("title", "Title"),
            Field("body", "Notice text", Kind.Multiline),
            Field("category", "Category", Kind.Choice, choices = {
                listOf("general", "admission", "exam", "event", "holiday", "routine").map { it to cap(it) }
            }),
        ),
        submit = { v, _ ->
            Api.request("POST", "/admin/notices", body(v))
            "Notice published."
        },
    ),
    "password" to FormSpec(
        title = "Change password", intro = "Other devices will be signed out.", submitLabel = "Change password",
        fields = listOf(Field("current_password", "Current password", Kind.Password), Field("new_password", "New password (8+ characters)", Kind.Password)),
        submit = { v, _ ->
            Session.save(Api.obj("POST", "/me/password", body(v)))
            "Password changed."
        },
    ),
)
