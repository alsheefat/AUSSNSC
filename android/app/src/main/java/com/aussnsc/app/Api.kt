package com.aussnsc.app

import android.content.Context
import android.content.SharedPreferences
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import org.json.JSONTokener
import java.io.IOException
import java.util.concurrent.TimeUnit

class ApiException(message: String, val code: Int = 0) : Exception(message)

/** org.json returns the string "null" for JSON null with optString, so go through isNull. */
fun JSONObject.str(key: String, def: String = ""): String = if (isNull(key)) def else optString(key, def)

fun JSONArray.objects(): List<JSONObject> = (0 until length()).mapNotNull { optJSONObject(it) }

fun JSONObject.list(key: String): List<JSONObject> = optJSONArray(key)?.objects() ?: emptyList()

/** Login state, kept in memory (observable by Compose) and in private app storage. */
object Session {
    private var prefs: SharedPreferences? = null

    var access by mutableStateOf<String?>(null)
        private set
    var user by mutableStateOf<JSONObject?>(null)
        private set
    var theme by mutableStateOf("system")
        private set
    var refresh: String? = null
        private set

    fun init(context: Context) {
        val p = context.applicationContext.getSharedPreferences("aussnsc_session", Context.MODE_PRIVATE)
        prefs = p
        access = p.getString("access", null)
        refresh = p.getString("refresh", null)
        theme = p.getString("theme", "system") ?: "system"
        user = p.getString("user", null)?.let { s -> try { JSONObject(s) } catch (e: Exception) { null } }
    }

    val loggedIn: Boolean get() = access != null

    val role: String
        get() = if (!loggedIn) "guest" else (user?.str("role", "public") ?: "public")

    fun save(tokens: JSONObject) {
        val u = tokens.getJSONObject("user")
        access = tokens.getString("access_token")
        refresh = tokens.getString("refresh_token")
        user = u
        prefs?.edit()
            ?.putString("access", access)
            ?.putString("refresh", refresh)
            ?.putString("user", u.toString())
            ?.apply()
    }

    fun updateUser(u: JSONObject) {
        user = u
        prefs?.edit()?.putString("user", u.toString())?.apply()
    }

    fun setTheme(value: String) {
        theme = value
        prefs?.edit()?.putString("theme", value)?.apply()
    }

    fun clear() {
        access = null
        refresh = null
        user = null
        prefs?.edit()?.remove("access")?.remove("refresh")?.remove("user")?.apply()
    }
}

object Api {
    private val base: String = BuildConfig.API_BASE_URL.trimEnd('/')
    private val JSON = "application/json; charset=utf-8".toMediaType()
    private val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(75, TimeUnit.SECONDS)   // free Render servers can take ~1 minute to wake up
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    /** "https://x.onrender.com/uploads/a.pdf" from "/uploads/a.pdf" */
    fun fileUrl(path: String): String =
        if (path.startsWith("http")) path else BuildConfig.API_BASE_URL.substringBefore("/api/").trimEnd('/') + path

    private fun send(method: String, path: String, body: JSONObject?, token: String?): Pair<Int, String> {
        val needsBody = method == "POST" || method == "PUT" || method == "PATCH"
        val requestBody = if (needsBody) (body ?: JSONObject()).toString().toRequestBody(JSON) else null
        val builder = Request.Builder().url(base + path).header("Accept", "application/json")
        if (token != null) builder.header("Authorization", "Bearer $token")
        builder.method(method, requestBody)
        val result: Pair<Int, String> = try {
            client.newCall(builder.build()).execute().use { resp -> Pair(resp.code, resp.body?.string() ?: "") }
        } catch (e: IOException) {
            throw ApiException("Can't reach the server. Check your internet connection. (The free server may take up to a minute to wake up - please try again.)")
        }
        return result
    }

    private fun tryRefresh(): Boolean {
        val rt = Session.refresh ?: return false
        return try {
            val res = send("POST", "/auth/refresh", JSONObject().put("refresh_token", rt), null)
            if (res.first == 200) {
                Session.save(JSONObject(res.second))
                true
            } else {
                Session.clear()
                false
            }
        } catch (e: Exception) {
            false
        }
    }

    private fun parse(code: Int, text: String): Any? {
        val value: Any? = if (text.isBlank()) null else try { JSONTokener(text).nextValue() } catch (e: Exception) { null }
        if (code in 200..299) return value
        var message = "Something went wrong (error $code)"
        if (value is JSONObject) {
            val d = value.opt("detail")
            if (d is String) {
                message = d
            } else if (d is JSONArray) {
                val joined = (0 until d.length())
                    .mapNotNull { d.optJSONObject(it)?.optString("msg") }
                    .joinToString("\n") { it.removePrefix("Value error, ") }
                if (joined.isNotBlank()) message = joined
            }
        }
        throw ApiException(message, code)
    }

    /** Returns JSONObject, JSONArray or null. Refreshes the access token once on 401. */
    suspend fun request(method: String, path: String, body: JSONObject? = null, auth: Boolean = true): Any? =
        withContext(Dispatchers.IO) {
            var res = send(method, path, body, if (auth) Session.access else null)
            if (res.first == 401 && auth && Session.refresh != null && tryRefresh()) {
                res = send(method, path, body, Session.access)
            }
            parse(res.first, res.second)
        }

    suspend fun obj(method: String, path: String, body: JSONObject? = null, auth: Boolean = true): JSONObject =
        request(method, path, body, auth) as? JSONObject ?: JSONObject()

    suspend fun arr(path: String, auth: Boolean = true): JSONArray =
        request("GET", path, null, auth) as? JSONArray ?: JSONArray()

    // ---- account helpers ----

    suspend fun login(identifier: String, password: String) {
        val body = JSONObject().put("identifier", identifier).put("password", password)
        Session.save(obj("POST", "/auth/login", body, false))
    }

    suspend fun register(name: String, phone: String, email: String, password: String) {
        val body = JSONObject().put("full_name", name).put("password", password)
        if (phone.isNotBlank()) body.put("phone", phone)
        if (email.isNotBlank()) body.put("email", email)
        Session.save(obj("POST", "/auth/register", body, false))
    }

    suspend fun googleExchange(firebaseIdToken: String) {
        Session.save(obj("POST", "/auth/google", JSONObject().put("id_token", firebaseIdToken), false))
    }

    suspend fun me() {
        Session.updateUser(obj("GET", "/me"))
    }
}
