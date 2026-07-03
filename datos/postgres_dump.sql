--
-- PostgreSQL database dump
--

\restrict 8CPFQvdUssSBnncvxUGvB9dNJ1lft0Gx70XWA79YTwZ1eQ7A8V8qSC72rLCkSGh

-- Dumped from database version 16.14
-- Dumped by pg_dump version 16.14

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alert_history; Type: TABLE; Schema: public; Owner: iot
--

CREATE TABLE public.alert_history (
    id bigint NOT NULL,
    alert_id bigint NOT NULL,
    ts timestamp with time zone DEFAULT now() NOT NULL,
    old_status text,
    new_status text NOT NULL,
    user_id bigint,
    username text,
    comment text
);


ALTER TABLE public.alert_history OWNER TO iot;

--
-- Name: alert_history_id_seq; Type: SEQUENCE; Schema: public; Owner: iot
--

CREATE SEQUENCE public.alert_history_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.alert_history_id_seq OWNER TO iot;

--
-- Name: alert_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: iot
--

ALTER SEQUENCE public.alert_history_id_seq OWNED BY public.alert_history.id;


--
-- Name: alerts; Type: TABLE; Schema: public; Owner: iot
--

CREATE TABLE public.alerts (
    id bigint NOT NULL,
    node_id text NOT NULL,
    node_name text,
    district text,
    lat double precision,
    lon double precision,
    ts bigint NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    responded_at timestamp with time zone,
    responded_by bigint,
    confidence real,
    source text DEFAULT 'camera'::text,
    det_class text,
    det_count integer,
    video_url text,
    status text DEFAULT 'pendiente'::text NOT NULL,
    risk_level text,
    temp_c real,
    turb_v real,
    humedad real,
    ph real,
    nivel_agua real,
    audio_rms real,
    audio_peak integer,
    sats integer,
    is_synthetic boolean DEFAULT false NOT NULL,
    CONSTRAINT alerts_risk_level_check CHECK ((risk_level = ANY (ARRAY['bajo'::text, 'medio'::text, 'alto'::text, 'critico'::text]))),
    CONSTRAINT alerts_status_check CHECK ((status = ANY (ARRAY['pendiente'::text, 'en-revision'::text, 'respondida'::text, 'resuelta'::text, 'falsa-alarma'::text, 'descartada'::text])))
);


ALTER TABLE public.alerts OWNER TO iot;

--
-- Name: alerts_id_seq; Type: SEQUENCE; Schema: public; Owner: iot
--

CREATE SEQUENCE public.alerts_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.alerts_id_seq OWNER TO iot;

--
-- Name: alerts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: iot
--

ALTER SEQUENCE public.alerts_id_seq OWNED BY public.alerts.id;


--
-- Name: anomalies; Type: TABLE; Schema: public; Owner: iot
--

CREATE TABLE public.anomalies (
    id bigint NOT NULL,
    node_id text NOT NULL,
    ts timestamp with time zone NOT NULL,
    type text,
    detail text
);


ALTER TABLE public.anomalies OWNER TO iot;

--
-- Name: anomalies_id_seq; Type: SEQUENCE; Schema: public; Owner: iot
--

CREATE SEQUENCE public.anomalies_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.anomalies_id_seq OWNER TO iot;

--
-- Name: anomalies_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: iot
--

ALTER SEQUENCE public.anomalies_id_seq OWNED BY public.anomalies.id;


--
-- Name: detections; Type: TABLE; Schema: public; Owner: iot
--

CREATE TABLE public.detections (
    id bigint NOT NULL,
    node_id text NOT NULL,
    ts timestamp with time zone NOT NULL,
    score real,
    threshold_used real,
    seq integer
);


ALTER TABLE public.detections OWNER TO iot;

--
-- Name: detections_id_seq; Type: SEQUENCE; Schema: public; Owner: iot
--

CREATE SEQUENCE public.detections_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.detections_id_seq OWNER TO iot;

--
-- Name: detections_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: iot
--

ALTER SEQUENCE public.detections_id_seq OWNED BY public.detections.id;


--
-- Name: detector_params; Type: TABLE; Schema: public; Owner: iot
--

CREATE TABLE public.detector_params (
    key text NOT NULL,
    value_num double precision,
    value_txt text,
    value_type text DEFAULT 'num'::text NOT NULL,
    min_num double precision,
    max_num double precision,
    description text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_by bigint,
    CONSTRAINT detector_params_value_type_check CHECK ((value_type = ANY (ARRAY['num'::text, 'txt'::text, 'bool'::text])))
);


ALTER TABLE public.detector_params OWNER TO iot;

--
-- Name: events; Type: TABLE; Schema: public; Owner: iot
--

CREATE TABLE public.events (
    id bigint NOT NULL,
    ts timestamp with time zone DEFAULT now() NOT NULL,
    user_id bigint,
    username text,
    action text NOT NULL,
    entity text,
    entity_id text,
    detail jsonb,
    ip text
);


ALTER TABLE public.events OWNER TO iot;

--
-- Name: events_id_seq; Type: SEQUENCE; Schema: public; Owner: iot
--

CREATE SEQUENCE public.events_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.events_id_seq OWNER TO iot;

--
-- Name: events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: iot
--

ALTER SEQUENCE public.events_id_seq OWNED BY public.events.id;


--
-- Name: heartbeats; Type: TABLE; Schema: public; Owner: iot
--

CREATE TABLE public.heartbeats (
    id bigint NOT NULL,
    node_id text NOT NULL,
    ts timestamp with time zone NOT NULL,
    battery_pct integer,
    chip_temp_c real,
    uptime_s bigint,
    threshold real,
    status text
);


ALTER TABLE public.heartbeats OWNER TO iot;

--
-- Name: heartbeats_id_seq; Type: SEQUENCE; Schema: public; Owner: iot
--

CREATE SEQUENCE public.heartbeats_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.heartbeats_id_seq OWNER TO iot;

--
-- Name: heartbeats_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: iot
--

ALTER SEQUENCE public.heartbeats_id_seq OWNED BY public.heartbeats.id;


--
-- Name: node_sensors; Type: TABLE; Schema: public; Owner: iot
--

CREATE TABLE public.node_sensors (
    id bigint NOT NULL,
    node_id text NOT NULL,
    sensor text NOT NULL,
    installed boolean DEFAULT true NOT NULL
);


ALTER TABLE public.node_sensors OWNER TO iot;

--
-- Name: node_sensors_id_seq; Type: SEQUENCE; Schema: public; Owner: iot
--

CREATE SEQUENCE public.node_sensors_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.node_sensors_id_seq OWNER TO iot;

--
-- Name: node_sensors_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: iot
--

ALTER SEQUENCE public.node_sensors_id_seq OWNED BY public.node_sensors.id;


--
-- Name: node_status_history; Type: TABLE; Schema: public; Owner: iot
--

CREATE TABLE public.node_status_history (
    id bigint NOT NULL,
    node_id text NOT NULL,
    ts timestamp with time zone NOT NULL,
    old_status text,
    new_status text NOT NULL
);


ALTER TABLE public.node_status_history OWNER TO iot;

--
-- Name: node_status_history_id_seq; Type: SEQUENCE; Schema: public; Owner: iot
--

CREATE SEQUENCE public.node_status_history_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.node_status_history_id_seq OWNER TO iot;

--
-- Name: node_status_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: iot
--

ALTER SEQUENCE public.node_status_history_id_seq OWNED BY public.node_status_history.id;


--
-- Name: nodes; Type: TABLE; Schema: public; Owner: iot
--

CREATE TABLE public.nodes (
    node_id text NOT NULL,
    node_name text,
    district text,
    lat double precision,
    lon double precision,
    alt double precision,
    status text DEFAULT 'UNKNOWN'::text NOT NULL,
    battery_pct integer,
    chip_temp_c real,
    threshold real,
    uptime_s bigint,
    first_seen timestamp with time zone DEFAULT now() NOT NULL,
    last_seen timestamp with time zone DEFAULT now() NOT NULL,
    last_heartbeat timestamp with time zone,
    last_reading timestamp with time zone,
    is_simulated boolean DEFAULT false NOT NULL,
    risk_level text DEFAULT 'bajo'::text NOT NULL,
    risk_score real DEFAULT 0 NOT NULL,
    CONSTRAINT nodes_risk_level_check CHECK ((risk_level = ANY (ARRAY['bajo'::text, 'medio'::text, 'alto'::text, 'critico'::text]))),
    CONSTRAINT nodes_status_check CHECK ((status = ANY (ARRAY['ONLINE'::text, 'OFFLINE'::text, 'COMPROMISED'::text, 'UNKNOWN'::text])))
);


ALTER TABLE public.nodes OWNER TO iot;

--
-- Name: sensor_readings; Type: TABLE; Schema: public; Owner: iot
--

CREATE TABLE public.sensor_readings (
    id bigint NOT NULL,
    node_id text NOT NULL,
    ts timestamp with time zone DEFAULT now() NOT NULL,
    temp_c real,
    turb_raw integer,
    turb_v real,
    humedad real,
    ph real,
    nivel_agua real,
    audio_conf real,
    extra jsonb
);


ALTER TABLE public.sensor_readings OWNER TO iot;

--
-- Name: sensor_readings_id_seq; Type: SEQUENCE; Schema: public; Owner: iot
--

CREATE SEQUENCE public.sensor_readings_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sensor_readings_id_seq OWNER TO iot;

--
-- Name: sensor_readings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: iot
--

ALTER SEQUENCE public.sensor_readings_id_seq OWNED BY public.sensor_readings.id;


--
-- Name: sessions; Type: TABLE; Schema: public; Owner: iot
--

CREATE TABLE public.sessions (
    id text NOT NULL,
    user_id bigint NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    ip text,
    user_agent text
);


ALTER TABLE public.sessions OWNER TO iot;

--
-- Name: system_config; Type: TABLE; Schema: public; Owner: iot
--

CREATE TABLE public.system_config (
    key text NOT NULL,
    value jsonb,
    description text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.system_config OWNER TO iot;

--
-- Name: users; Type: TABLE; Schema: public; Owner: iot
--

CREATE TABLE public.users (
    id bigint NOT NULL,
    username text NOT NULL,
    password_hash text NOT NULL,
    role text DEFAULT 'operador'::text NOT NULL,
    full_name text,
    active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    last_login timestamp with time zone,
    CONSTRAINT users_role_check CHECK ((role = ANY (ARRAY['admin'::text, 'operador'::text])))
);


ALTER TABLE public.users OWNER TO iot;

--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: iot
--

CREATE SEQUENCE public.users_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.users_id_seq OWNER TO iot;

--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: iot
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: videos; Type: TABLE; Schema: public; Owner: iot
--

CREATE TABLE public.videos (
    id bigint NOT NULL,
    node_id text NOT NULL,
    received_at timestamp with time zone NOT NULL,
    file_path text NOT NULL,
    file_size_kb integer
);


ALTER TABLE public.videos OWNER TO iot;

--
-- Name: videos_id_seq; Type: SEQUENCE; Schema: public; Owner: iot
--

CREATE SEQUENCE public.videos_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.videos_id_seq OWNER TO iot;

--
-- Name: videos_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: iot
--

ALTER SEQUENCE public.videos_id_seq OWNED BY public.videos.id;


--
-- Name: alert_history id; Type: DEFAULT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.alert_history ALTER COLUMN id SET DEFAULT nextval('public.alert_history_id_seq'::regclass);


--
-- Name: alerts id; Type: DEFAULT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.alerts ALTER COLUMN id SET DEFAULT nextval('public.alerts_id_seq'::regclass);


--
-- Name: anomalies id; Type: DEFAULT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.anomalies ALTER COLUMN id SET DEFAULT nextval('public.anomalies_id_seq'::regclass);


--
-- Name: detections id; Type: DEFAULT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.detections ALTER COLUMN id SET DEFAULT nextval('public.detections_id_seq'::regclass);


--
-- Name: events id; Type: DEFAULT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.events ALTER COLUMN id SET DEFAULT nextval('public.events_id_seq'::regclass);


--
-- Name: heartbeats id; Type: DEFAULT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.heartbeats ALTER COLUMN id SET DEFAULT nextval('public.heartbeats_id_seq'::regclass);


--
-- Name: node_sensors id; Type: DEFAULT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.node_sensors ALTER COLUMN id SET DEFAULT nextval('public.node_sensors_id_seq'::regclass);


--
-- Name: node_status_history id; Type: DEFAULT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.node_status_history ALTER COLUMN id SET DEFAULT nextval('public.node_status_history_id_seq'::regclass);


--
-- Name: sensor_readings id; Type: DEFAULT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.sensor_readings ALTER COLUMN id SET DEFAULT nextval('public.sensor_readings_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Name: videos id; Type: DEFAULT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.videos ALTER COLUMN id SET DEFAULT nextval('public.videos_id_seq'::regclass);


--
-- Data for Name: alert_history; Type: TABLE DATA; Schema: public; Owner: iot
--

COPY public.alert_history (id, alert_id, ts, old_status, new_status, user_id, username, comment) FROM stdin;
5	3	2026-07-03 03:31:36.262045+00	\N	pendiente	\N	\N	migración desde SQLite
6	5	2026-07-03 03:31:36.262045+00	\N	pendiente	\N	\N	migración desde SQLite
7	6	2026-07-03 03:31:36.262045+00	\N	pendiente	\N	\N	migración desde SQLite
10	9	2026-07-03 03:41:09.395901+00	\N	pendiente	\N	\N	creada por el detector
11	9	2026-07-03 03:49:00.407678+00	pendiente	respondida	2	operador1	Brigada notificada, zona revisada
19	15	2026-07-03 04:06:14.225043+00	\N	pendiente	\N	\N	creada por el detector
20	16	2026-07-03 04:06:48.601024+00	\N	pendiente	\N	\N	creada por el generador sintético
21	17	2026-07-03 04:06:48.603691+00	\N	pendiente	\N	\N	creada por el generador sintético
22	18	2026-07-03 04:06:48.605712+00	\N	pendiente	\N	\N	creada por el generador sintético
23	19	2026-07-03 04:06:48.607578+00	\N	pendiente	\N	\N	creada por el generador sintético
24	20	2026-07-03 04:06:48.609683+00	\N	pendiente	\N	\N	creada por el generador sintético
25	21	2026-07-03 04:06:48.611345+00	\N	pendiente	\N	\N	creada por el generador sintético
26	22	2026-07-03 04:06:48.612796+00	\N	pendiente	\N	\N	creada por el generador sintético
27	23	2026-07-03 04:06:48.61404+00	\N	pendiente	\N	\N	creada por el generador sintético
28	24	2026-07-03 04:06:48.615178+00	\N	pendiente	\N	\N	creada por el generador sintético
29	25	2026-07-03 04:06:48.616419+00	\N	pendiente	\N	\N	creada por el generador sintético
30	26	2026-07-03 04:06:48.617573+00	\N	pendiente	\N	\N	creada por el generador sintético
31	27	2026-07-03 04:06:48.61865+00	\N	pendiente	\N	\N	creada por el generador sintético
32	28	2026-07-03 04:06:48.619706+00	\N	pendiente	\N	\N	creada por el generador sintético
33	29	2026-07-03 04:06:48.621084+00	\N	pendiente	\N	\N	creada por el generador sintético
34	30	2026-07-03 04:06:48.622313+00	\N	pendiente	\N	\N	creada por el generador sintético
42	32	2026-07-03 17:28:31.471221+00	\N	pendiente	\N	\N	creada por el generador sintético
43	32	2026-07-03 17:28:31.494357+00	pendiente	respondida	1	admin	prueba cola
44	32	2026-07-03 17:28:31.556338+00	respondida	resuelta	1	admin	cerrada
\.


--
-- Data for Name: alerts; Type: TABLE DATA; Schema: public; Owner: iot
--

COPY public.alerts (id, node_id, node_name, district, lat, lon, ts, created_at, responded_at, responded_by, confidence, source, det_class, det_count, video_url, status, risk_level, temp_c, turb_v, humedad, ph, nivel_agua, audio_rms, audio_peak, sats, is_synthetic) FROM stdin;
3	esp32-01	Nodo SJL-01	San Juan de Lurigancho	-11.962	-77	1782439946265	2026-07-03 03:31:36.262045+00	\N	\N	0.806	camera	Mosquito	70	/home/luis/Escritorio/SERVER IOT/Sistema-Integrado-IOT/datos/clips/esp32-01/20260625-211221.webm	pendiente	\N	23.19	1.026	\N	\N	\N	\N	\N	\N	f
5	esp32-01	Nodo SJL-01	San Juan de Lurigancho	-11.962	-77	1782591886197	2026-07-03 03:31:36.262045+00	\N	\N	0.903	camera	Mosquito	106	/home/luis/Escritorio/SERVER IOT/Sistema-Integrado-IOT/datos/clips/esp32-01/20260627-152442.webm	pendiente	\N	25.31	0.216	\N	\N	\N	\N	\N	\N	f
6	esp32-01	Nodo SJL-01	San Juan de Lurigancho	-11.962	-77	1782594489665	2026-07-03 03:31:36.262045+00	\N	\N	0.795	camera	Mosquito	50	/home/luis/Escritorio/SERVER IOT/Sistema-Integrado-IOT/datos/clips/esp32-01/20260627-160805.webm	pendiente	\N	25.25	0.205	\N	\N	\N	\N	\N	\N	f
9	esp32-01	Nodo SJL-01	San Juan de Lurigancho	-11.9615	-77.0012	1783050069395	2026-07-03 03:41:09.395901+00	2026-07-03 03:49:00.407678+00	2	0.986	camera	Mosquito	51	/home/luis/Escritorio/SERVER IOT/Sistema-Integrado-IOT/datos/clips/esp32-01/20260702-224103.webm	respondida	\N	27.4	1.45	\N	\N	\N	\N	\N	7	f
15	esp32-99	esp32-99	desconocido	-12.020045	-76.994719	1783051574224	2026-07-03 04:06:14.225043+00	\N	\N	0.987	camera	Mosquito	92	/home/luis/Escritorio/SERVER IOT/Sistema-Integrado-IOT/datos/clips/esp32-99/20260702-230608.webm	pendiente	\N	28	2.4	75	\N	\N	\N	\N	7	f
16	esp32-99	Nodo SIM esp32-99	Simulado	-12.019611163815066	-76.9922427454542	1782639917522	2026-07-03 04:06:48.601024+00	\N	\N	0.724	camera	Mosquito	10	\N	pendiente	critico	29	2.6	78	\N	\N	\N	\N	\N	t
17	esp32-99	Nodo SIM esp32-99	Simulado	-12.022882648967052	-76.99722889438767	1782684382851	2026-07-03 04:06:48.603691+00	\N	\N	0.765	camera	Mosquito	2	\N	pendiente	critico	29	2.6	78	\N	\N	\N	\N	\N	t
18	esp32-99	Nodo SIM esp32-99	Simulado	-12.023307766285345	-76.99099160849205	1782711125958	2026-07-03 04:06:48.605712+00	\N	\N	0.862	camera	Mosquito	5	\N	pendiente	critico	29	2.6	78	\N	\N	\N	\N	\N	t
19	esp32-99	Nodo SIM esp32-99	Simulado	-12.01838294246216	-76.99313620716865	1782730256782	2026-07-03 04:06:48.607578+00	\N	\N	0.797	camera	Mosquito	6	\N	pendiente	critico	29	2.6	78	\N	\N	\N	\N	\N	t
20	esp32-99	Nodo SIM esp32-99	Simulado	-12.022043567858498	-76.99264443001306	1782918986642	2026-07-03 04:06:48.609683+00	\N	\N	0.948	camera	Mosquito	3	\N	pendiente	critico	29	2.6	78	\N	\N	\N	\N	\N	t
21	esp32-99	Nodo SIM esp32-99	Simulado	-12.023485607791816	-76.99367728262752	1782985395946	2026-07-03 04:06:48.611345+00	\N	\N	0.845	camera	Mosquito	12	\N	pendiente	critico	29	2.6	78	\N	\N	\N	\N	\N	t
22	esp32-99	Nodo SIM esp32-99	Simulado	-12.018752873322194	-76.99770048977358	1782705603538	2026-07-03 04:06:48.612796+00	\N	\N	0.851	camera	Mosquito	9	\N	pendiente	critico	29	2.6	78	\N	\N	\N	\N	\N	t
23	esp32-99	Nodo SIM esp32-99	Simulado	-12.017779781356015	-76.99690597354754	1782978329962	2026-07-03 04:06:48.61404+00	\N	\N	0.971	camera	Mosquito	9	\N	pendiente	critico	29	2.6	78	\N	\N	\N	\N	\N	t
24	esp32-99	Nodo SIM esp32-99	Simulado	-12.019889836716725	-76.9929088206007	1782976159521	2026-07-03 04:06:48.615178+00	\N	\N	0.955	camera	Mosquito	6	\N	pendiente	critico	29	2.6	78	\N	\N	\N	\N	\N	t
25	esp32-99	Nodo SIM esp32-99	Simulado	-12.021757649729665	-76.99122208666103	1782768701539	2026-07-03 04:06:48.616419+00	\N	\N	0.964	camera	Mosquito	7	\N	pendiente	critico	29	2.6	78	\N	\N	\N	\N	\N	t
26	esp32-99	Nodo SIM esp32-99	Simulado	-12.01992013132714	-76.99690435983734	1782924138879	2026-07-03 04:06:48.617573+00	\N	\N	0.817	camera	Mosquito	11	\N	pendiente	critico	29	2.6	78	\N	\N	\N	\N	\N	t
27	esp32-99	Nodo SIM esp32-99	Simulado	-12.018825078909108	-76.99179774620158	1782679778720	2026-07-03 04:06:48.61865+00	\N	\N	0.816	camera	Mosquito	9	\N	pendiente	critico	29	2.6	78	\N	\N	\N	\N	\N	t
28	esp32-99	Nodo SIM esp32-99	Simulado	-12.017927224379713	-76.9982052663406	1783031035727	2026-07-03 04:06:48.619706+00	\N	\N	0.761	camera	Mosquito	12	\N	pendiente	critico	29	2.6	78	\N	\N	\N	\N	\N	t
29	esp32-99	Nodo SIM esp32-99	Simulado	-12.02272594158982	-76.99858288594359	1782771176569	2026-07-03 04:06:48.621084+00	\N	\N	0.789	camera	Mosquito	4	\N	pendiente	critico	29	2.6	78	\N	\N	\N	\N	\N	t
30	esp32-99	Nodo SIM esp32-99	Simulado	-12.021100403947326	-76.99869102836749	1782956333120	2026-07-03 04:06:48.622313+00	\N	\N	0.785	camera	Mosquito	11	\N	pendiente	critico	29	2.6	78	\N	\N	\N	\N	\N	t
32	esp32-01	Nodo SJL-01	San Juan de Lurigancho	-11.9615	-77.0012	1783099711468	2026-07-03 17:28:31.471221+00	2026-07-03 17:28:31.494357+00	1	0.93	camera	Mosquito	9	\N	resuelta	alto	27	1.2	\N	\N	\N	\N	\N	\N	t
\.


--
-- Data for Name: anomalies; Type: TABLE DATA; Schema: public; Owner: iot
--

COPY public.anomalies (id, node_id, ts, type, detail) FROM stdin;
1	esp32-01	2026-06-25 05:07:24+00	offline	offline
2	esp32-01	2026-06-25 23:28:57+00	offline	offline
3	esp32-01	2026-06-25 23:29:58+00	offline	offline
4	esp32-01	2026-06-25 23:31:07+00	offline	offline
5	esp32-01	2026-06-25 23:32:28+00	offline	offline
6	esp32-01	2026-06-25 23:32:45+00	offline	offline
7	esp32-01	2026-06-25 23:32:47+00	offline	offline
8	esp32-01	2026-06-25 23:33:20+00	offline	offline
9	esp32-01	2026-06-25 23:33:38+00	offline	offline
10	esp32-01	2026-06-25 23:35:04+00	offline	offline
11	esp32-01	2026-06-25 23:36:09+00	offline	offline
12	esp32-01	2026-06-25 23:37:00+00	offline	offline
13	esp32-01	2026-06-25 23:41:39+00	offline	offline
14	esp32-01	2026-06-25 23:42:39+00	offline	offline
15	esp32-01	2026-06-25 23:45:25+00	offline	offline
16	esp32-01	2026-06-26 00:05:13+00	offline	offline
17	esp32-01	2026-06-26 00:06:17+00	offline	offline
18	esp32-01	2026-06-26 00:07:18+00	offline	offline
19	esp32-01	2026-06-26 00:08:14+00	offline	offline
20	esp32-01	2026-06-26 00:28:23+00	offline	offline
21	esp32-01	2026-06-26 00:28:44+00	offline	offline
22	esp32-01	2026-06-26 00:32:07+00	offline	offline
23	esp32-01	2026-06-26 00:42:01+00	offline	offline
24	esp32-01	2026-06-26 00:42:42+00	offline	offline
25	esp32-01	2026-06-26 00:44:46+00	offline	offline
26	esp32-01	2026-06-26 00:45:11+00	offline	offline
27	esp32-01	2026-06-26 00:45:35+00	offline	offline
28	esp32-01	2026-06-26 00:46:02+00	offline	offline
29	esp32-01	2026-06-26 00:48:14+00	offline	offline
30	esp32-01	2026-06-26 00:54:12+00	offline	offline
31	esp32-01	2026-06-26 00:55:14+00	offline	offline
32	esp32-01	2026-06-26 00:56:11+00	offline	offline
33	esp32-01	2026-06-26 00:56:37+00	offline	offline
34	esp32-01	2026-06-26 01:02:37+00	offline	offline
35	esp32-01	2026-06-26 01:03:21+00	offline	offline
36	esp32-01	2026-06-26 01:05:14+00	offline	offline
37	esp32-01	2026-06-26 01:05:30+00	offline	offline
38	esp32-01	2026-06-26 01:08:46+00	offline	offline
39	esp32-01	2026-06-26 01:11:20+00	offline	offline
40	esp32-01	2026-06-26 01:12:46+00	offline	offline
41	esp32-01	2026-06-26 01:14:05+00	offline	offline
42	esp32-01	2026-06-26 01:16:00+00	offline	offline
43	esp32-01	2026-06-26 01:36:06+00	offline	offline
44	esp32-01	2026-06-26 01:39:41+00	offline	offline
45	esp32-01	2026-06-26 01:42:37+00	offline	offline
46	esp32-01	2026-06-26 01:43:18+00	offline	offline
47	esp32-01	2026-06-26 01:45:32+00	offline	offline
48	esp32-01	2026-06-26 01:45:58+00	offline	offline
49	esp32-01	2026-06-26 01:46:23+00	offline	offline
50	esp32-01	2026-06-26 01:46:50+00	offline	offline
51	esp32-01	2026-06-26 01:47:14+00	offline	offline
52	esp32-01	2026-06-26 01:47:40+00	offline	offline
53	esp32-01	2026-06-26 01:48:04+00	offline	offline
54	esp32-01	2026-06-26 01:48:28+00	offline	offline
55	esp32-01	2026-06-26 01:48:52+00	offline	offline
56	esp32-01	2026-06-26 01:49:17+00	offline	offline
57	esp32-01	2026-06-26 01:49:23+00	offline	offline
58	esp32-01	2026-06-26 01:49:44+00	offline	offline
59	esp32-01	2026-06-26 01:50:11+00	offline	offline
60	esp32-01	2026-06-26 01:50:34+00	offline	offline
61	esp32-01	2026-06-26 01:50:59+00	offline	offline
62	esp32-01	2026-06-26 01:51:24+00	offline	offline
63	esp32-01	2026-06-26 01:51:48+00	offline	offline
64	esp32-01	2026-06-26 01:52:13+00	offline	offline
65	esp32-01	2026-06-26 01:52:41+00	offline	offline
66	esp32-01	2026-06-26 01:53:02+00	offline	offline
67	esp32-01	2026-06-26 01:53:15+00	offline	offline
68	esp32-01	2026-06-26 01:53:42+00	offline	offline
69	esp32-01	2026-06-26 01:54:07+00	offline	offline
70	esp32-01	2026-06-26 01:54:39+00	offline	offline
71	esp32-01	2026-06-26 01:58:07+00	offline	offline
72	esp32-01	2026-06-26 01:58:38+00	offline	offline
73	esp32-01	2026-06-26 01:59:03+00	offline	offline
74	esp32-01	2026-06-26 01:59:29+00	offline	offline
75	esp32-01	2026-06-26 02:00:02+00	offline	offline
76	esp32-01	2026-06-26 02:00:26+00	offline	offline
77	esp32-01	2026-06-26 02:00:56+00	offline	offline
78	esp32-01	2026-06-26 02:01:23+00	offline	offline
79	esp32-01	2026-06-26 02:01:48+00	offline	offline
80	esp32-01	2026-06-26 02:02:19+00	offline	offline
81	esp32-01	2026-06-26 02:02:40+00	offline	offline
82	esp32-01	2026-06-26 02:03:03+00	offline	offline
83	esp32-01	2026-06-26 02:03:19+00	offline	offline
84	esp32-01	2026-06-26 02:03:29+00	offline	offline
85	esp32-01	2026-06-26 02:04:01+00	offline	offline
86	esp32-01	2026-06-26 02:04:28+00	offline	offline
87	esp32-01	2026-06-26 02:04:52+00	offline	offline
88	esp32-01	2026-06-26 02:05:18+00	offline	offline
89	esp32-01	2026-06-26 02:05:43+00	offline	offline
90	esp32-01	2026-06-26 02:06:05+00	offline	offline
91	esp32-01	2026-06-26 02:09:26+00	offline	offline
92	esp32-01	2026-06-26 02:10:17+00	offline	offline
93	esp32-01	2026-06-26 02:12:32+00	offline	offline
94	esp32-01	2026-06-26 02:20:09+00	offline	offline
95	esp32-01	2026-06-26 02:20:10+00	offline	offline
96	esp32-01	2026-06-26 02:23:57+00	offline	offline
97	esp32-01	2026-06-27 16:45:08+00	offline	offline
98	esp32-01	2026-06-27 16:47:14+00	offline	offline
99	esp32-01	2026-06-27 16:48:02+00	offline	offline
100	esp32-01	2026-06-27 16:49:03+00	offline	offline
101	esp32-01	2026-06-27 16:50:12+00	offline	offline
102	esp32-01	2026-06-27 16:51:00+00	offline	offline
103	esp32-01	2026-06-27 16:51:38+00	offline	offline
104	esp32-01	2026-06-27 16:51:54+00	offline	offline
105	esp32-01	2026-06-27 16:52:50+00	offline	offline
106	esp32-01	2026-06-27 16:53:49+00	offline	offline
107	esp32-01	2026-06-27 16:55:11+00	offline	offline
108	esp32-01	2026-06-27 16:56:58+00	offline	offline
109	esp32-01	2026-06-27 16:58:35+00	offline	offline
110	esp32-01	2026-06-27 17:01:35+00	offline	offline
111	esp32-01	2026-06-27 17:02:16+00	offline	offline
112	esp32-01	2026-06-27 17:03:12+00	offline	offline
113	esp32-01	2026-06-27 17:04:30+00	offline	offline
114	esp32-01	2026-06-27 17:05:33+00	offline	offline
115	esp32-01	2026-06-27 17:07:34+00	offline	offline
116	esp32-01	2026-06-27 17:08:31+00	offline	offline
117	esp32-01	2026-06-27 17:09:02+00	offline	offline
118	esp32-01	2026-06-27 17:10:07+00	offline	offline
119	esp32-01	2026-06-27 17:15:45+00	offline	offline
120	esp32-01	2026-06-27 17:16:14+00	offline	offline
121	esp32-01	2026-06-27 17:17:03+00	offline	offline
122	esp32-01	2026-06-27 17:19:43+00	offline	offline
123	esp32-01	2026-06-27 18:10:50+00	offline	offline
124	esp32-01	2026-06-27 18:10:51+00	offline	offline
125	esp32-01	2026-06-27 18:50:32+00	offline	offline
126	esp32-01	2026-06-27 19:53:10+00	offline	offline
127	esp32-01	2026-06-27 19:53:38+00	offline	offline
128	esp32-01	2026-06-27 19:54:08+00	offline	offline
129	esp32-01	2026-06-27 19:54:51+00	offline	offline
130	esp32-01	2026-06-27 19:55:18+00	offline	offline
131	esp32-01	2026-06-27 19:57:27+00	offline	offline
132	esp32-01	2026-06-27 19:59:03+00	offline	offline
133	esp32-01	2026-06-27 19:59:41+00	offline	offline
134	esp32-01	2026-06-27 20:00:11+00	offline	offline
135	esp32-01	2026-06-27 20:01:36+00	offline	offline
136	esp32-01	2026-06-27 20:02:48+00	offline	offline
137	esp32-01	2026-06-27 20:04:20+00	offline	offline
138	esp32-01	2026-06-27 20:04:52+00	offline	offline
139	esp32-01	2026-06-27 20:05:54+00	offline	offline
140	esp32-01	2026-06-27 20:06:20+00	offline	offline
141	esp32-01	2026-06-27 20:10:30+00	offline	offline
142	esp32-01	2026-06-27 20:12:16+00	offline	offline
143	esp32-01	2026-06-27 20:12:54+00	offline	offline
144	esp32-01	2026-06-27 20:15:37+00	offline	offline
145	esp32-01	2026-06-27 20:16:36+00	offline	offline
146	esp32-01	2026-06-27 20:17:21+00	offline	offline
147	esp32-01	2026-06-27 20:17:49+00	offline	offline
148	esp32-01	2026-06-27 20:19:28+00	offline	offline
149	esp32-01	2026-06-27 20:19:55+00	offline	offline
150	esp32-01	2026-06-27 20:22:49+00	offline	offline
151	esp32-01	2026-06-27 20:23:20+00	offline	offline
152	esp32-01	2026-06-27 20:24:20+00	offline	offline
153	esp32-01	2026-06-27 20:24:53+00	offline	offline
154	esp32-01	2026-06-27 20:25:19+00	offline	offline
155	esp32-01	2026-06-27 20:25:45+00	offline	offline
156	esp32-01	2026-06-27 20:26:28+00	offline	offline
157	esp32-01	2026-06-27 20:27:02+00	offline	offline
158	esp32-01	2026-06-27 20:27:25+00	offline	offline
159	esp32-01	2026-06-27 20:27:50+00	offline	offline
160	esp32-01	2026-06-27 20:28:17+00	offline	offline
161	esp32-01	2026-06-27 20:28:45+00	offline	offline
162	esp32-01	2026-06-27 20:30:58+00	offline	offline
163	esp32-01	2026-06-27 20:31:32+00	offline	offline
164	esp32-01	2026-06-27 20:32:15+00	offline	offline
165	esp32-01	2026-06-27 20:33:28+00	offline	offline
166	esp32-01	2026-06-27 20:34:08+00	offline	offline
167	esp32-01	2026-06-27 20:34:33+00	offline	offline
168	esp32-01	2026-06-27 20:34:59+00	offline	offline
169	esp32-01	2026-06-27 20:35:39+00	offline	offline
170	esp32-01	2026-06-27 20:36:17+00	offline	offline
171	esp32-01	2026-06-27 20:36:44+00	offline	offline
172	esp32-01	2026-06-27 20:37:13+00	offline	offline
173	esp32-01	2026-06-27 20:37:14+00	offline	offline
174	esp32-01	2026-06-27 20:37:37+00	offline	offline
175	esp32-01	2026-06-27 20:38:02+00	offline	offline
176	esp32-01	2026-06-27 20:38:30+00	offline	offline
177	esp32-01	2026-06-27 20:38:56+00	offline	offline
178	esp32-01	2026-06-27 20:39:20+00	offline	offline
179	esp32-01	2026-06-27 20:39:47+00	offline	offline
180	esp32-01	2026-06-27 20:40:29+00	offline	offline
181	esp32-01	2026-06-27 20:41:33+00	offline	offline
182	esp32-01	2026-06-27 20:42:20+00	offline	offline
183	esp32-01	2026-06-27 20:42:50+00	offline	offline
184	esp32-01	2026-06-27 20:43:17+00	offline	offline
185	esp32-01	2026-06-27 20:43:42+00	offline	offline
186	esp32-01	2026-06-27 20:44:09+00	offline	offline
187	esp32-01	2026-06-27 20:44:34+00	offline	offline
188	esp32-01	2026-06-27 20:45:40+00	offline	offline
189	esp32-01	2026-06-27 20:46:59+00	offline	offline
190	esp32-01	2026-06-27 20:47:41+00	offline	offline
191	esp32-01	2026-06-27 20:48:05+00	offline	offline
192	esp32-01	2026-06-27 20:48:31+00	offline	offline
193	esp32-01	2026-06-27 20:49:14+00	offline	offline
194	esp32-01	2026-06-27 20:49:39+00	offline	offline
195	esp32-01	2026-06-27 20:50:17+00	offline	offline
196	esp32-01	2026-06-27 20:51:01+00	offline	offline
197	esp32-01	2026-06-27 20:51:27+00	offline	offline
198	esp32-01	2026-06-27 20:52:54+00	offline	offline
199	esp32-01	2026-06-27 20:53:27+00	offline	offline
200	esp32-01	2026-06-27 20:54:00+00	offline	offline
201	esp32-01	2026-06-27 20:54:26+00	offline	offline
202	esp32-01	2026-06-27 20:54:50+00	offline	offline
203	esp32-01	2026-06-27 20:56:03+00	offline	offline
204	esp32-01	2026-06-27 20:56:54+00	offline	offline
205	esp32-01	2026-06-27 20:57:28+00	offline	offline
206	esp32-01	2026-06-27 20:57:56+00	offline	offline
207	esp32-01	2026-06-27 20:59:40+00	offline	offline
208	esp32-01	2026-06-27 21:00:08+00	offline	offline
209	esp32-01	2026-06-27 21:00:34+00	offline	offline
210	esp32-01	2026-06-27 21:01:25+00	offline	offline
211	esp32-01	2026-06-27 21:01:48+00	offline	offline
212	esp32-01	2026-06-27 21:02:14+00	offline	offline
213	esp32-01	2026-06-27 21:02:46+00	offline	offline
214	esp32-01	2026-06-27 21:03:34+00	offline	offline
215	esp32-01	2026-06-27 21:04:56+00	offline	offline
216	esp32-01	2026-06-27 21:05:34+00	offline	offline
217	esp32-01	2026-06-27 21:06:21+00	offline	offline
218	esp32-01	2026-06-27 21:06:45+00	offline	offline
219	esp32-01	2026-06-27 21:07:12+00	offline	offline
220	esp32-01	2026-06-27 21:07:40+00	offline	offline
221	esp32-01	2026-06-27 21:08:23+00	offline	offline
222	esp32-01	2026-06-27 21:08:58+00	offline	offline
223	esp32-01	2026-06-27 21:09:26+00	offline	offline
224	esp32-01	2026-06-27 21:10:13+00	offline	offline
225	esp32-01	2026-06-27 21:10:39+00	offline	offline
226	esp32-01	2026-06-27 21:18:09+00	offline	offline
227	esp32-01	2026-06-27 21:18:43+00	offline	offline
228	esp32-01	2026-06-27 21:19:38+00	offline	offline
229	esp32-01	2026-06-27 21:32:55+00	offline	offline
230	esp32-01	2026-06-27 21:34:13+00	offline	offline
231	esp32-01	2026-06-27 21:47:06+00	offline	offline
232	esp32-01	2026-06-27 21:47:59+00	offline	offline
233	esp32-01	2026-06-27 21:53:44+00	offline	offline
234	esp32-01	2026-06-27 21:55:01+00	offline	offline
235	esp32-01	2026-06-27 22:03:22+00	offline	offline
236	esp32-01	2026-06-27 22:11:51+00	offline	offline
237	esp32-01	2026-06-27 22:12:25+00	offline	offline
238	esp32-01	2026-06-27 22:17:41+00	offline	offline
239	esp32-01	2026-06-27 22:20:21+00	offline	offline
240	esp32-01	2026-06-27 22:21:35+00	offline	offline
241	esp32-01	2026-06-27 22:21:52+00	offline	offline
242	esp32-01	2026-06-27 22:22:33+00	offline	offline
243	esp32-01	2026-06-27 22:29:17+00	offline	offline
244	esp32-01	2026-06-27 22:31:44+00	offline	offline
245	esp32-01	2026-06-27 22:32:00+00	offline	offline
246	esp32-01	2026-06-27 22:48:15+00	offline	offline
247	esp32-01	2026-06-27 23:07:58+00	offline	offline
248	esp32-01	2026-06-27 23:07:59+00	offline	offline
249	esp32-01	2026-06-27 23:15:34+00	offline	offline
250	esp32-01	2026-06-27 23:19:12+00	offline	offline
251	esp32-01	2026-06-27 23:33:18+00	offline	offline
252	esp32-01	2026-06-27 23:33:37+00	offline	offline
253	esp32-01	2026-06-27 23:35:45+00	offline	offline
254	esp32-01	2026-07-03 02:48:20+00	offline	offline
255	esp32-01	2026-07-03 03:40:07+00	offline	offline
256	esp32-01	2026-07-03 03:48:22+00	offline	offline
257	esp32-01	2026-07-03 04:02:11+00	offline	offline
258	esp32-01	2026-07-03 04:19:03+00	offline	offline
259	esp32-01	2026-07-03 04:30:03+00	offline	offline
260	esp32-01	2026-07-03 04:30:28+00	offline	offline
261	esp32-01	2026-07-03 04:31:36+00	offline	offline
262	esp32-01	2026-07-03 17:09:48+00	offline	offline
263	esp32-01	2026-07-03 17:10:35+00	offline	offline
264	esp32-01	2026-07-03 17:28:00+00	offline	offline
\.


--
-- Data for Name: detections; Type: TABLE DATA; Schema: public; Owner: iot
--

COPY public.detections (id, node_id, ts, score, threshold_used, seq) FROM stdin;
2	esp32-01	2026-06-25 22:57:21+00	0.9	\N	\N
3	esp32-01	2026-06-25 23:28:34+00	0.54	1	2
4	esp32-01	2026-06-25 23:30:49+00	0.6	1	2
5	esp32-01	2026-06-25 23:32:27+00	0.37	1	2
6	esp32-01	2026-06-25 23:33:19+00	0.4	1	2
7	esp32-01	2026-06-25 23:35:51+00	0.45	1	2
8	esp32-01	2026-06-25 23:36:42+00	0.42	1	2
9	esp32-01	2026-06-25 23:42:21+00	0.61	1	2
10	esp32-01	2026-06-25 23:45:07+00	0.34	1	2
11	esp32-01	2026-06-26 00:05:58+00	0.57	0.601	2
12	esp32-01	2026-06-26 00:07:56+00	0.58	0.601	2
13	esp32-01	2026-06-26 00:28:22+00	0.34	0.601	3
14	esp32-01	2026-06-26 00:41:41+00	0.63	0.421	2
15	esp32-01	2026-06-26 00:44:27+00	0.55	0.421	1
16	esp32-01	2026-06-26 00:44:51+00	0.52	0.421	1
17	esp32-01	2026-06-26 00:45:15+00	0.52	0.421	1
18	esp32-01	2026-06-26 00:45:39+00	0.5	0.421	1
19	esp32-01	2026-06-26 00:55:51+00	0.37	0.663	1
20	esp32-01	2026-06-26 01:05:01+00	0.32	0.39	2
21	esp32-01	2026-06-26 01:08:33+00	0.54	0.39	2
22	esp32-01	2026-06-26 01:42:16+00	0.34	0.405	4
23	esp32-01	2026-06-26 01:45:12+00	0.27	0.405	1
24	esp32-01	2026-06-26 01:45:39+00	0.57	0.405	1
25	esp32-01	2026-06-26 01:46:02+00	0.6	0.405	1
26	esp32-01	2026-06-26 01:46:28+00	0.6	0.405	1
27	esp32-01	2026-06-26 01:46:55+00	0.6	0.405	1
28	esp32-01	2026-06-26 01:47:19+00	0.6	0.405	1
29	esp32-01	2026-06-26 01:47:45+00	0.55	0.405	1
30	esp32-01	2026-06-26 01:48:09+00	0.55	0.405	1
31	esp32-01	2026-06-26 01:48:33+00	0.58	0.405	1
32	esp32-01	2026-06-26 01:48:57+00	0.43	0.405	1
33	esp32-01	2026-06-26 01:49:22+00	0.57	0.405	1
34	esp32-01	2026-06-26 01:49:49+00	0.6	0.405	1
35	esp32-01	2026-06-26 01:50:16+00	0.5	0.405	1
36	esp32-01	2026-06-26 01:50:40+00	0.6	0.405	1
37	esp32-01	2026-06-26 01:51:04+00	0.57	0.405	1
38	esp32-01	2026-06-26 01:51:29+00	0.55	0.405	1
39	esp32-01	2026-06-26 01:51:53+00	0.39	0.405	1
40	esp32-01	2026-06-26 01:52:19+00	0.63	0.405	1
41	esp32-01	2026-06-26 01:52:46+00	0.43	0.405	1
42	esp32-01	2026-06-26 01:53:20+00	0.6	0.405	1
43	esp32-01	2026-06-26 01:53:47+00	0.52	0.405	1
44	esp32-01	2026-06-26 01:54:12+00	0.6	0.405	1
45	esp32-01	2026-06-26 01:57:47+00	0.54	0.405	1
46	esp32-01	2026-06-26 01:58:13+00	0.54	0.405	1
47	esp32-01	2026-06-26 01:58:43+00	0.57	0.405	1
48	esp32-01	2026-06-26 01:59:08+00	0.4	0.405	1
49	esp32-01	2026-06-26 01:59:36+00	0.52	0.405	1
50	esp32-01	2026-06-26 02:00:07+00	0.6	0.405	1
51	esp32-01	2026-06-26 02:00:34+00	0.46	0.405	1
52	esp32-01	2026-06-26 02:01:02+00	0.57	0.405	1
53	esp32-01	2026-06-26 02:01:28+00	0.54	0.405	1
54	esp32-01	2026-06-26 02:01:53+00	0.34	0.405	1
55	esp32-01	2026-06-26 02:02:24+00	0.52	0.405	1
56	esp32-01	2026-06-26 02:03:39+00	0.46	0.405	1
57	esp32-01	2026-06-26 02:04:06+00	0.6	0.405	1
58	esp32-01	2026-06-26 02:04:33+00	0.48	0.405	1
59	esp32-01	2026-06-26 02:04:57+00	0.5	0.405	1
60	esp32-01	2026-06-26 02:05:23+00	0.52	0.405	2
61	esp32-01	2026-06-26 02:05:49+00	0.52	0.405	1
62	esp32-01	2026-06-26 02:09:06+00	0.02	0.292	4
63	esp32-01	2026-06-26 02:09:58+00	0.24	0.292	2
64	esp32-01	2026-06-26 02:12:12+00	0.24	0.292	2
65	esp32-01	2026-06-27 16:46:59+00	0.19	0.292	2
66	esp32-01	2026-06-27 16:47:35+00	0.12	0.112	2
67	esp32-01	2026-06-27 16:48:37+00	0.39	0.112	2
68	esp32-01	2026-06-27 16:49:53+00	0.3	0.112	2
69	esp32-01	2026-06-27 16:50:35+00	0.06	0.112	2
70	esp32-01	2026-06-27 16:51:19+00	0.09	0.112	2
71	esp32-01	2026-06-27 16:52:23+00	0.17	0.112	1
72	esp32-01	2026-06-27 16:53:22+00	0.07	0.112	2
73	esp32-01	2026-06-27 16:54:50+00	0.1	0.112	2
74	esp32-01	2026-06-27 16:56:42+00	0.21	0.112	2
75	esp32-01	2026-06-27 16:58:09+00	0.24	0.202	2
76	esp32-01	2026-06-27 17:01:19+00	0.27	0.202	2
77	esp32-01	2026-06-27 17:01:59+00	0.37	0.202	2
78	esp32-01	2026-06-27 17:02:54+00	0.43	0.202	2
79	esp32-01	2026-06-27 17:04:03+00	0.34	0.202	2
80	esp32-01	2026-06-27 17:05:06+00	0.52	0.202	2
81	esp32-01	2026-06-27 17:07:07+00	0.45	0.202	2
82	esp32-01	2026-06-27 17:08:15+00	0.12	0.202	2
83	esp32-01	2026-06-27 17:08:46+00	0.36	0.202	2
84	esp32-01	2026-06-27 17:09:41+00	0.4	0.202	2
85	esp32-01	2026-06-27 17:15:25+00	0.24	0.202	2
86	esp32-01	2026-06-27 17:15:54+00	0.22	0.202	1
87	esp32-01	2026-06-27 17:16:44+00	0.16	0.202	2
88	esp32-01	2026-06-27 17:19:21+00	0.17	0.202	2
89	esp32-01	2026-06-27 19:52:51+00	0.23	0.202	2
90	esp32-01	2026-06-27 19:53:19+00	0.24	0.202	1
91	esp32-01	2026-06-27 19:53:47+00	0.21	0.202	1
92	esp32-01	2026-06-27 19:54:32+00	0.23	0.202	2
93	esp32-01	2026-06-27 19:54:59+00	0.15	0.202	1
94	esp32-01	2026-06-27 19:57:07+00	0.2	0.202	2
95	esp32-01	2026-06-27 19:58:44+00	0.07	0.202	2
96	esp32-01	2026-06-27 19:59:22+00	0.23	0.202	2
97	esp32-01	2026-06-27 19:59:52+00	0.32	0.202	1
98	esp32-01	2026-06-27 20:01:14+00	0.17	0.202	2
99	esp32-01	2026-06-27 20:02:29+00	0.37	0.202	2
100	esp32-01	2026-06-27 20:04:01+00	0.3	0.202	2
101	esp32-01	2026-06-27 20:04:33+00	0.36	0.202	1
102	esp32-01	2026-06-27 20:05:34+00	0.19	0.202	2
103	esp32-01	2026-06-27 20:06:02+00	0.01	0.202	1
104	esp32-01	2026-06-27 20:10:11+00	0.09	0.202	2
105	esp32-01	2026-06-27 20:11:57+00	0.43	0.202	2
106	esp32-01	2026-06-27 20:12:33+00	0.11	0.202	2
107	esp32-01	2026-06-27 20:15:18+00	0.21	0.202	2
108	esp32-01	2026-06-27 20:16:16+00	0.21	0.202	3
109	esp32-01	2026-06-27 20:17:02+00	0.39	0.202	2
110	esp32-01	2026-06-27 20:17:31+00	0.15	0.202	1
111	esp32-01	2026-06-27 20:19:08+00	0.19	0.202	2
112	esp32-01	2026-06-27 20:19:35+00	0.1	0.202	1
113	esp32-01	2026-06-27 20:22:29+00	0.21	0.202	3
114	esp32-01	2026-06-27 20:23:00+00	0.21	0.202	1
115	esp32-01	2026-06-27 20:24:01+00	0.16	0.12	2
116	esp32-01	2026-06-27 20:24:33+00	0.12	0.12	1
117	esp32-01	2026-06-27 20:24:59+00	0.27	0.12	1
118	esp32-01	2026-06-27 20:25:26+00	0.26	0.12	1
119	esp32-01	2026-06-27 20:26:09+00	0.08	0.12	2
120	esp32-01	2026-06-27 20:26:41+00	0.2	0.12	1
121	esp32-01	2026-06-27 20:27:06+00	0.06	0.12	1
122	esp32-01	2026-06-27 20:27:30+00	0.09	0.12	1
123	esp32-01	2026-06-27 20:27:56+00	0.06	0.12	1
124	esp32-01	2026-06-27 20:28:26+00	0.13	0.12	1
125	esp32-01	2026-06-27 20:30:39+00	0.11	0.12	2
126	esp32-01	2026-06-27 20:31:11+00	0.07	0.12	1
127	esp32-01	2026-06-27 20:31:55+00	0.07	0.12	2
128	esp32-01	2026-06-27 20:33:04+00	0.16	0.12	2
129	esp32-01	2026-06-27 20:33:50+00	0.11	0.12	2
130	esp32-01	2026-06-27 20:34:14+00	0.17	0.12	1
131	esp32-01	2026-06-27 20:34:40+00	0.24	0.12	1
132	esp32-01	2026-06-27 20:35:19+00	0.12	0.12	2
133	esp32-01	2026-06-27 20:35:57+00	0.12	0.12	2
134	esp32-01	2026-06-27 20:36:22+00	0.09	0.12	1
135	esp32-01	2026-06-27 20:36:53+00	0.13	0.12	1
136	esp32-01	2026-06-27 20:37:18+00	0.11	0.12	1
137	esp32-01	2026-06-27 20:37:43+00	0.13	0.12	1
138	esp32-01	2026-06-27 20:38:12+00	0.17	0.12	1
139	esp32-01	2026-06-27 20:38:38+00	0.14	0.12	1
140	esp32-01	2026-06-27 20:39:02+00	0.01	0.12	1
141	esp32-01	2026-06-27 20:39:31+00	0.36	0.12	1
142	esp32-01	2026-06-27 20:40:12+00	0.16	0.12	2
143	esp32-01	2026-06-27 20:41:12+00	0.16	0.12	2
144	esp32-01	2026-06-27 20:41:58+00	0.23	0.12	2
145	esp32-01	2026-06-27 20:42:26+00	0.31	0.12	1
146	esp32-01	2026-06-27 20:42:58+00	0.02	0.12	1
147	esp32-01	2026-06-27 20:43:23+00	0.28	0.12	1
148	esp32-01	2026-06-27 20:43:49+00	0.12	0.12	1
149	esp32-01	2026-06-27 20:44:15+00	0.24	0.12	1
150	esp32-01	2026-06-27 20:45:21+00	0.26	0.12	2
151	esp32-01	2026-06-27 20:46:40+00	0.22	0.12	2
152	esp32-01	2026-06-27 20:47:22+00	0.18	0.12	2
153	esp32-01	2026-06-27 20:47:45+00	0.27	0.12	1
154	esp32-01	2026-06-27 20:48:10+00	0.21	0.12	1
155	esp32-01	2026-06-27 20:48:55+00	0.14	0.12	2
156	esp32-01	2026-06-27 20:49:20+00	0.16	0.12	1
157	esp32-01	2026-06-27 20:49:58+00	0.08	0.12	2
158	esp32-01	2026-06-27 20:50:41+00	0.16	0.12	2
159	esp32-01	2026-06-27 20:51:06+00	0.31	0.12	1
160	esp32-01	2026-06-27 20:52:34+00	0.07	0.12	2
161	esp32-01	2026-06-27 20:53:07+00	0.16	0.12	1
162	esp32-01	2026-06-27 20:53:39+00	0.27	0.12	1
163	esp32-01	2026-06-27 20:54:05+00	0	0.12	1
164	esp32-01	2026-06-27 20:54:31+00	0.04	0.12	1
165	esp32-01	2026-06-27 20:55:41+00	0.07	0.12	2
166	esp32-01	2026-06-27 20:56:34+00	0.12	0.12	2
167	esp32-01	2026-06-27 20:57:04+00	0.19	0.12	1
168	esp32-01	2026-06-27 20:57:37+00	0.01	0.12	1
169	esp32-01	2026-06-27 20:59:18+00	0.06	0.12	2
170	esp32-01	2026-06-27 20:59:48+00	0.28	0.12	1
171	esp32-01	2026-06-27 21:01:04+00	0.15	0.12	1
172	esp32-01	2026-06-27 21:01:29+00	0.4	0.12	1
173	esp32-01	2026-06-27 21:01:54+00	0.13	0.12	1
174	esp32-01	2026-06-27 21:02:26+00	0.12	0.12	1
175	esp32-01	2026-06-27 21:03:15+00	0.07	0.12	2
176	esp32-01	2026-06-27 21:04:35+00	0.22	0.12	2
177	esp32-01	2026-06-27 21:05:15+00	0.05	0.12	2
178	esp32-01	2026-06-27 21:06:03+00	0.11	0.12	2
179	esp32-01	2026-06-27 21:06:26+00	0.12	0.12	1
180	esp32-01	2026-06-27 21:06:51+00	0.01	0.12	1
181	esp32-01	2026-06-27 21:07:20+00	0.21	0.12	1
182	esp32-01	2026-06-27 21:07:57+00	0.16	0.12	2
183	esp32-01	2026-06-27 21:08:39+00	0.11	0.12	2
184	esp32-01	2026-06-27 21:09:06+00	0.42	0.12	1
185	esp32-01	2026-06-27 21:09:54+00	0.15	0.12	2
186	esp32-01	2026-06-27 21:18:51+00	0.61	0.12	1
187	esp32-01	2026-06-27 21:19:02+00	0.68	0.12	2
188	esp32-01	2026-06-27 21:19:12+00	0.7	0.12	4
189	esp32-01	2026-06-27 21:19:22+00	0.69	0.12	5
190	esp32-01	2026-06-27 21:19:44+00	0.68	0.12	1
191	esp32-01	2026-06-27 21:19:54+00	0.52	0.12	2
192	esp32-01	2026-06-27 21:20:04+00	0.16	0.12	4
193	esp32-01	2026-06-27 21:38:05+00	0.12	0.741	2
194	esp32-01	2026-06-27 21:38:16+00	0.02	0.741	3
195	esp32-01	2026-06-27 21:38:26+00	0.63	0.741	4
196	esp32-01	2026-06-27 21:38:38+00	0.26	0.741	5
197	esp32-01	2026-06-27 21:38:50+00	0.2	0.741	6
198	esp32-01	2026-06-27 21:39:00+00	0.32	0.741	7
199	esp32-01	2026-06-27 21:39:11+00	0.01	0.741	8
200	esp32-01	2026-06-27 21:39:22+00	0.63	0.741	9
201	esp32-01	2026-06-27 21:39:34+00	0.37	0.741	10
202	esp32-01	2026-06-27 21:39:44+00	0.37	0.741	11
203	esp32-01	2026-06-27 21:39:56+00	0.32	0.741	12
204	esp32-01	2026-06-27 21:40:06+00	0.46	0.741	13
205	esp32-01	2026-06-27 21:40:16+00	0.37	0.741	14
206	esp32-01	2026-06-27 21:40:30+00	0.17	0.741	15
207	esp32-01	2026-06-27 21:40:51+00	0.13	0.741	16
208	esp32-01	2026-06-27 21:41:06+00	0.17	0.741	17
209	esp32-01	2026-06-27 21:41:17+00	0.09	0.741	18
210	esp32-01	2026-06-27 21:41:27+00	0.63	0.741	19
211	esp32-01	2026-06-27 21:42:00+00	0.19	0.741	20
212	esp32-01	2026-06-27 21:42:12+00	0.17	0.741	21
213	esp32-01	2026-06-27 21:42:33+00	0.14	0.741	22
214	esp32-01	2026-06-27 21:42:44+00	0.02	0.741	23
215	esp32-01	2026-06-27 21:42:54+00	0.63	0.741	24
216	esp32-01	2026-06-27 21:43:13+00	0.17	0.741	25
217	esp32-01	2026-06-27 21:43:34+00	0.17	0.741	26
218	esp32-01	2026-06-27 21:43:45+00	0.13	0.741	27
219	esp32-01	2026-06-27 21:44:10+00	0	0.741	28
220	esp32-01	2026-06-27 21:44:20+00	0.58	0.741	29
221	esp32-01	2026-06-27 21:44:30+00	0.19	0.175	31
222	esp32-01	2026-06-27 21:44:51+00	0.13	0.175	32
223	esp32-01	2026-06-27 21:45:12+00	0.12	0.175	33
224	esp32-01	2026-06-27 21:45:23+00	0.01	0.175	34
225	esp32-01	2026-06-27 21:45:33+00	0.6	0.175	35
226	esp32-01	2026-06-27 21:45:43+00	0.15	0.175	36
227	esp32-01	2026-06-27 21:45:54+00	0.26	0.175	37
228	esp32-01	2026-06-27 21:46:15+00	0.11	0.175	38
229	esp32-01	2026-06-27 21:46:25+00	0	0.175	39
230	esp32-01	2026-06-27 21:46:36+00	0.69	0.175	40
231	esp32-01	2026-06-27 21:46:50+00	0.19	0.175	41
232	esp32-01	2026-06-27 21:47:28+00	0.2	0.175	1
233	esp32-01	2026-06-27 21:47:39+00	0.12	0.175	3
234	esp32-01	2026-06-27 21:49:05+00	0.57	0.175	2
235	esp32-01	2026-06-27 21:57:21+00	0.26	0.347	2
236	esp32-01	2026-06-27 22:00:50+00	0.31	0.347	3
237	esp32-01	2026-06-27 22:02:16+00	0.26	0.347	4
238	esp32-01	2026-06-27 22:02:28+00	0.34	0.347	5
239	esp32-01	2026-06-27 22:02:39+00	0.43	0.347	6
240	esp32-01	2026-06-27 22:02:51+00	0.24	0.347	7
241	esp32-01	2026-06-27 22:03:01+00	0.3	0.347	8
242	esp32-01	2026-06-27 22:03:28+00	0.24	0.347	1
243	esp32-01	2026-06-27 22:04:06+00	0.3	0.269	3
244	esp32-01	2026-06-27 22:10:45+00	0.43	0.269	4
245	esp32-01	2026-06-27 22:12:14+00	0.69	0.269	1
246	esp32-01	2026-06-27 22:19:20+00	0.32	0.484	2
247	esp32-01	2026-06-27 22:19:33+00	0.43	0.484	3
248	esp32-01	2026-06-27 22:19:49+00	0.34	0.484	4
249	esp32-01	2026-06-27 22:20:11+00	0.37	0.484	5
250	esp32-01	2026-06-27 22:20:27+00	0.54	0.484	1
251	esp32-01	2026-06-27 22:20:37+00	0.66	0.331	3
252	esp32-01	2026-06-27 22:21:07+00	0.31	0.331	4
253	esp32-01	2026-06-27 22:21:25+00	0.39	0.331	5
254	esp32-01	2026-06-27 22:21:42+00	0.58	0.331	1
255	esp32-01	2026-06-27 22:22:19+00	0.05	0.331	2
256	esp32-01	2026-06-27 22:23:12+00	0.28	0.331	2
257	esp32-01	2026-06-27 22:28:38+00	0.36	0.331	3
258	esp32-01	2026-06-27 22:28:56+00	0.36	0.331	4
259	esp32-01	2026-06-27 22:29:07+00	0.37	0.331	5
260	esp32-01	2026-06-27 22:29:38+00	0.32	0.331	2
261	esp32-01	2026-06-27 22:31:22+00	0.32	0.331	3
262	esp32-01	2026-06-27 22:31:34+00	0.39	0.331	4
263	esp32-01	2026-06-27 22:34:09+00	0.23	0.331	2
264	esp32-01	2026-06-27 22:34:30+00	0.27	0.331	3
265	esp32-01	2026-06-27 22:34:44+00	0.32	0.331	4
266	esp32-01	2026-06-27 22:35:06+00	0.34	0.331	5
267	esp32-01	2026-06-27 22:38:07+00	0.4	0.331	6
268	esp32-01	2026-06-27 22:38:53+00	0.4	0.331	7
269	esp32-01	2026-06-27 22:40:03+00	0.34	0.331	8
270	esp32-01	2026-06-27 22:40:16+00	0.13	0.331	9
271	esp32-01	2026-06-27 22:40:27+00	0.09	0.331	10
272	esp32-01	2026-06-27 22:41:00+00	0.32	0.331	11
273	esp32-01	2026-06-27 22:42:32+00	0.43	0.331	12
274	esp32-01	2026-06-27 22:47:55+00	0.12	0.331	14
275	esp32-01	2026-06-27 22:48:30+00	0.12	0.331	2
276	esp32-01	2026-06-27 22:49:52+00	0.17	0.331	3
277	esp32-01	2026-06-27 22:50:18+00	0.27	0.331	4
278	esp32-01	2026-06-27 22:57:24+00	0.23	0.331	5
279	esp32-01	2026-06-27 22:57:48+00	0.34	0.331	6
280	esp32-01	2026-06-27 22:59:17+00	0.36	0.331	8
281	esp32-01	2026-06-27 23:08:16+00	0.69	0.331	2
282	esp32-01	2026-06-27 23:08:26+00	0.57	0.331	3
283	esp32-01	2026-06-27 23:08:36+00	0.69	0.331	4
284	esp32-01	2026-06-27 23:08:47+00	0.68	0.331	5
285	esp32-01	2026-06-27 23:08:57+00	0.4	0.331	6
286	esp32-01	2026-06-27 23:09:07+00	0.64	0.331	7
287	esp32-01	2026-06-27 23:09:19+00	0.39	0.331	8
288	esp32-01	2026-06-27 23:09:29+00	0.42	0.331	9
289	esp32-01	2026-06-27 23:09:40+00	0.34	0.331	10
290	esp32-01	2026-06-27 23:09:50+00	0.68	0.331	11
291	esp32-01	2026-06-27 23:10:01+00	0.52	0.331	12
292	esp32-01	2026-06-27 23:10:11+00	0.5	0.331	13
293	esp32-01	2026-06-27 23:10:21+00	0.52	0.331	14
294	esp32-01	2026-06-27 23:10:40+00	0.18	0.331	15
295	esp32-01	2026-06-27 23:11:22+00	0.5	0.331	16
296	esp32-01	2026-06-27 23:11:37+00	0.48	0.331	17
297	esp32-01	2026-06-27 23:12:06+00	0.64	0.331	19
298	esp32-01	2026-06-27 23:12:22+00	0.2	0.331	20
299	esp32-01	2026-06-27 23:12:57+00	0.42	0.331	21
300	esp32-01	2026-06-27 23:13:07+00	0.68	0.331	22
301	esp32-01	2026-06-27 23:13:20+00	0.61	0.331	23
302	esp32-01	2026-06-27 23:13:30+00	0.7	0.331	24
303	esp32-01	2026-06-27 23:13:40+00	0.64	0.331	25
304	esp32-01	2026-06-27 23:13:50+00	0.31	0.331	26
305	esp32-01	2026-06-27 23:14:02+00	0.63	0.331	27
306	esp32-01	2026-06-27 23:14:14+00	0.55	0.331	28
307	esp32-01	2026-06-27 23:14:24+00	0.24	0.331	29
308	esp32-01	2026-06-27 23:14:35+00	0.64	0.331	30
309	esp32-01	2026-06-27 23:14:46+00	0.63	0.331	31
310	esp32-01	2026-06-27 23:14:58+00	0.63	0.331	32
311	esp32-01	2026-06-27 23:15:08+00	0.55	0.331	33
312	esp32-01	2026-06-27 23:15:19+00	0.58	0.331	34
313	esp32-01	2026-06-27 23:17:14+00	0.36	0.331	2
314	esp32-01	2026-06-27 23:29:06+00	0.32	0.331	4
315	esp32-01	2026-06-27 23:30:13+00	0.36	0.331	5
316	esp32-01	2026-06-27 23:31:27+00	0.45	0.331	6
317	esp32-01	2026-06-27 23:31:37+00	0.64	0.331	7
318	esp32-01	2026-06-27 23:31:48+00	0.63	0.331	8
319	esp32-01	2026-06-27 23:32:01+00	0.55	0.331	9
320	esp32-01	2026-06-27 23:32:12+00	0.42	0.331	10
321	esp32-01	2026-06-27 23:32:24+00	0.45	0.331	11
322	esp32-01	2026-06-27 23:32:39+00	0.37	0.331	12
323	esp32-01	2026-06-27 23:32:54+00	0.5	0.331	13
324	esp32-01	2026-06-27 23:33:08+00	0.5	0.331	14
325	esp32-01	2026-06-27 23:33:26+00	0.32	0.331	1
326	esp32-01	2026-06-27 23:33:51+00	0.34	0.331	1
327	esp32-01	2026-06-27 23:34:01+00	0.46	0.331	3
328	esp32-01	2026-06-27 23:34:13+00	0.37	0.331	4
329	esp32-01	2026-06-27 23:34:23+00	0.4	0.331	5
330	esp32-01	2026-06-27 23:34:34+00	0.55	0.331	6
331	esp32-01	2026-06-27 23:34:45+00	0.31	0.331	7
332	esp32-01	2026-06-27 23:34:56+00	0.42	0.331	8
333	esp32-01	2026-06-27 23:35:08+00	0.39	0.331	9
334	esp32-01	2026-06-27 23:35:20+00	0.57	0.331	10
335	esp32-01	2026-06-27 23:35:30+00	0.37	0.331	11
336	esp32-01	2026-06-27 23:38:10+00	0.4	0.331	2
337	esp32-01	2026-06-27 23:40:25+00	0.37	0.331	5
338	esp32-01	2026-06-27 23:40:42+00	0.28	0.331	6
339	esp32-01	2026-06-27 23:40:57+00	0.36	0.331	7
340	esp32-01	2026-06-27 23:41:08+00	0.5	0.331	8
341	esp32-01	2026-07-03 03:41:01+00	0.87	0.45	100
342	esp32-99	2026-07-03 04:06:07+00	0.9	0.45	2
343	esp32-99	2026-07-03 04:07:45+00	0.9	0.45	4
344	esp32-99	2026-07-03 04:08:22+00	0.9	0.45	7
\.


--
-- Data for Name: detector_params; Type: TABLE DATA; Schema: public; Owner: iot
--

COPY public.detector_params (key, value_num, value_txt, value_type, min_num, max_num, description, updated_at, updated_by) FROM stdin;
umbral_mosquito	1	\N	num	1	50	mínimo de objetos para 'mosquito'	2026-07-03 03:31:36.262045+00	\N
umbral_enjambre	10	\N	num	2	100	mínimo de objetos para 'enjambre'	2026-07-03 03:31:36.262045+00	\N
area_min	10	\N	num	1	500	área mínima de blob (px²)	2026-07-03 03:31:36.262045+00	\N
area_max	800	\N	num	50	10000	área máxima de blob (px²)	2026-07-03 03:31:36.262045+00	\N
aspect_min	0.2	\N	num	0.01	1	ratio w/h mínimo	2026-07-03 03:31:36.262045+00	\N
aspect_max	5	\N	num	1	20	ratio w/h máximo	2026-07-03 03:31:36.262045+00	\N
max_frame_ratio	0.02	\N	num	0.001	0.5	blob no puede superar este % del frame	2026-07-03 03:31:36.262045+00	\N
circularidad_min	0.1	\N	num	0	1	circularidad mínima del contorno	2026-07-03 03:31:36.262045+00	\N
persistencia_min	8	\N	num	1	60	frames consecutivos para confirmar	2026-07-03 03:31:36.262045+00	\N
dist_max	40	\N	num	5	300	px máx de movimiento entre frames (matching)	2026-07-03 03:31:36.262045+00	\N
max_movimiento_total	0.05	\N	num	0.005	0.9	si el movimiento supera este % del frame -> objeto grande	2026-07-03 03:31:36.262045+00	\N
mov_min	12	\N	num	0	200	desplazamiento mínimo total (px) para confirmar	2026-07-03 03:31:36.262045+00	\N
flow_min	0.6	\N	num	0	10	magnitud media mínima de flujo óptico (px/frame)	2026-07-03 03:31:36.262045+00	\N
ema_alpha	0.08	\N	num	0.01	1	suavizado EMA de la confianza	2026-07-03 03:31:36.262045+00	\N
conf_on	0.7	\N	num	0	1	umbral de encendido de alerta (histéresis)	2026-07-03 03:31:36.262045+00	\N
conf_off	0.3	\N	num	0	1	umbral de apagado de alerta (histéresis)	2026-07-03 03:31:36.262045+00	\N
mask_threshold	200	\N	num	1	255	umbral binario fijo de la máscara MOG2	2026-07-03 03:31:36.262045+00	\N
mog2_history	500	\N	num	50	2000	ventana temporal del sustractor de fondo	2026-07-03 03:31:36.262045+00	\N
mog2_var_threshold	50	\N	num	4	200	sensibilidad al cambio del MOG2	2026-07-03 03:31:36.262045+00	\N
proc_w	640	\N	num	160	1920	ancho de procesamiento	2026-07-03 03:31:36.262045+00	\N
proc_h	480	\N	num	120	1080	alto de procesamiento	2026-07-03 03:31:36.262045+00	\N
use_bilateral	0	\N	num	0	1	1 = denoise bilateral en vez de blur gaussiano	2026-07-03 03:31:36.262045+00	\N
clahe_enabled	0	\N	num	0	1	1 = ecualización CLAHE (costo CPU extra)	2026-07-03 03:31:36.262045+00	\N
noise_percentile	0	\N	num	0	99.9	umbral adaptativo por percentil de la máscara (0 = usar mask_threshold fijo)	2026-07-03 03:31:36.262045+00	\N
vel_min_px_s	0	\N	num	0	2000	velocidad mínima del track (px/s; 0 = sin filtro)	2026-07-03 03:31:36.262045+00	\N
vel_max_px_s	0	\N	num	0	5000	velocidad máxima del track (px/s; 0 = sin filtro)	2026-07-03 03:31:36.262045+00	\N
trayectoria_min_puntos	0	\N	num	0	60	puntos mínimos de trayectoria (0 = sin filtro)	2026-07-03 03:31:36.262045+00	\N
flow_downscale	1	\N	num	1	4	divisor de resolución para el flujo óptico (ARM)	2026-07-03 03:31:36.262045+00	\N
conf_min_alerta	0.7	\N	num	0	1	confianza pico mínima para ACEPTAR la alerta	2026-07-03 03:50:01.472239+00	1
\.


--
-- Data for Name: events; Type: TABLE DATA; Schema: public; Owner: iot
--

COPY public.events (id, ts, user_id, username, action, entity, entity_id, detail, ip) FROM stdin;
1	2026-07-03 03:27:35.104293+00	\N	smoke-test	alert.status	alert	1	{"new": "en-revision", "old": "pendiente", "comment": "prueba de transición"}	\N
2	2026-07-03 03:48:59.647222+00	\N	\N	login.failed	\N	\N	{"username": "admin"}	127.0.0.1
3	2026-07-03 03:48:59.890409+00	1	admin	login	\N	\N	\N	127.0.0.1
4	2026-07-03 03:49:00.146789+00	1	admin	user.create	user	2	{"role": "operador", "username": "operador1"}	\N
5	2026-07-03 03:49:00.389536+00	2	operador1	login	\N	\N	\N	127.0.0.1
6	2026-07-03 03:49:00.407678+00	2	operador1	alert.status	alert	9	{"new": "respondida", "old": "pendiente", "comment": "Brigada notificada, zona revisada"}	\N
7	2026-07-03 03:49:28.764928+00	2	operador1	alert.status	alert	1	{"new": "falsa-alarma", "old": "pendiente", "comment": "era una pelusa"}	\N
8	2026-07-03 03:49:28.774806+00	2	operador1	alert.status	alert	2	{"new": "descartada", "old": "pendiente", "comment": null}	\N
9	2026-07-03 03:49:28.834936+00	1	admin	config.detector	detector_params	\N	{"conf_min_alerta": 0.75}	\N
10	2026-07-03 03:49:28.856509+00	1	admin	alerts.synthetic	alert	\N	{"count": 5, "node_id": "esp32-01"}	\N
11	2026-07-03 03:50:01.47348+00	1	admin	config.detector	detector_params	\N	{"conf_min_alerta": 0.7}	\N
12	2026-07-03 04:02:33.83579+00	1	admin	login	\N	\N	\N	127.0.0.1
13	2026-07-03 04:02:33.868122+00	1	admin	logout	\N	\N	\N	\N
14	2026-07-03 04:06:48.555038+00	1	admin	login	\N	\N	\N	127.0.0.1
15	2026-07-03 04:32:52.080391+00	1	admin	login	\N	\N	\N	127.0.0.1
16	2026-07-03 04:33:36.463896+00	1	admin	alert.status	alert	8	{"new": "falsa-alarma", "old": "pendiente", "comment": null}	\N
17	2026-07-03 04:36:58.492728+00	1	admin	logout	\N	\N	\N	\N
18	2026-07-03 04:37:16.418127+00	\N	\N	login.failed	\N	\N	{"username": "operador1"}	127.0.0.1
19	2026-07-03 04:37:23.685782+00	\N	\N	login.failed	\N	\N	{"username": "operador1"}	127.0.0.1
20	2026-07-03 04:37:37.407473+00	\N	\N	login.failed	\N	\N	{"username": "operador1"}	127.0.0.1
21	2026-07-03 04:37:50.758109+00	2	operador1	login	\N	\N	\N	127.0.0.1
22	2026-07-03 04:38:45.824867+00	2	operador1	alert.status	alert	8	{"new": "descartada", "old": "falsa-alarma", "comment": null}	\N
23	2026-07-03 04:39:23.638171+00	2	operador1	alert.status	alert	1	{"new": "descartada", "old": "falsa-alarma", "comment": null}	\N
24	2026-07-03 04:39:32.337954+00	2	operador1	alert.status	alert	31	{"new": "en-revision", "old": "pendiente", "comment": null}	\N
25	2026-07-03 04:39:42.214845+00	2	operador1	alert.status	alert	31	{"new": "resuelta", "old": "en-revision", "comment": null}	\N
26	2026-07-03 04:40:11.278588+00	2	operador1	alert.status	alert	31	{"new": "falsa-alarma", "old": "resuelta", "comment": null}	\N
27	2026-07-03 17:11:01.831181+00	\N	\N	login.failed	\N	\N	{"username": "admin"}	127.0.0.1
28	2026-07-03 17:11:06.766485+00	1	admin	login	\N	\N	\N	127.0.0.1
29	2026-07-03 17:28:31.45352+00	1	admin	login	\N	\N	\N	127.0.0.1
30	2026-07-03 17:28:31.474989+00	1	admin	alerts.synthetic	alert	\N	{"count": 1, "node_id": "esp32-01"}	\N
31	2026-07-03 17:28:31.494357+00	1	admin	alert.status	alert	32	{"new": "respondida", "old": "pendiente", "comment": "prueba cola"}	\N
32	2026-07-03 17:28:31.556338+00	1	admin	alert.status	alert	32	{"new": "resuelta", "old": "respondida", "comment": "cerrada"}	\N
33	2026-07-03 17:28:31.585479+00	1	admin	alerts.synthetic	alert	\N	{"count": 1, "node_id": "esp32-01"}	\N
34	2026-07-03 17:28:31.622444+00	1	admin	alert.delete	alert	33	{"ts": 1783099711578, "node": "esp32-01", "motivo": "falsa alarma", "comment": "no era mosquito", "old_status": "pendiente"}	\N
35	2026-07-03 17:31:24.129613+00	1	admin	alert.delete	alert	7	{"ts": 1782601741901, "node": "esp32-01", "motivo": "falsa alarma", "comment": null, "old_status": "pendiente"}	\N
36	2026-07-03 18:08:11.885941+00	1	admin	login	\N	\N	\N	127.0.0.1
\.


--
-- Data for Name: heartbeats; Type: TABLE DATA; Schema: public; Owner: iot
--

COPY public.heartbeats (id, node_id, ts, battery_pct, chip_temp_c, uptime_s, threshold, status) FROM stdin;
2	esp32-01	2026-06-25 23:27:24+00	-1	35.2	23	1	alive
3	esp32-01	2026-06-25 23:29:12+00	-1	35.2	21	1	alive
4	esp32-01	2026-06-25 23:30:29+00	-1	35.2	20	1	alive
5	esp32-01	2026-06-25 23:31:22+00	-1	36.2	20	1	alive
6	esp32-01	2026-06-25 23:33:02+00	-1	36.2	21	1	alive
7	esp32-01	2026-06-25 23:33:53+00	-1	36.2	20	1	alive
8	esp32-01	2026-06-25 23:35:19+00	-1	37.2	21	1	alive
9	esp32-01	2026-06-25 23:36:24+00	-1	36.2	20	1	alive
10	esp32-01	2026-06-25 23:37:15+00	-1	36.2	20	1	alive
11	esp32-01	2026-06-25 23:41:54+00	-1	36.2	23	1	alive
12	esp32-01	2026-06-25 23:42:54+00	-1	36.2	20	1	alive
13	esp32-01	2026-06-25 23:45:40+00	-1	36.2	20	1	alive
14	esp32-01	2026-06-25 23:55:40+00	-1	36.2	620	0.601	alive
15	esp32-01	2026-06-26 00:05:47+00	-1	36.2	20	0.601	alive
16	esp32-01	2026-06-26 00:06:32+00	-1	36.2	20	0.601	alive
17	esp32-01	2026-06-26 00:07:46+00	-1	35.2	20	0.601	alive
18	esp32-01	2026-06-26 00:08:29+00	-1	38.2	20	0.601	alive
19	esp32-01	2026-06-26 00:18:29+00	-1	36.2	620	0.601	alive
20	esp32-01	2026-06-26 00:28:33+00	-1	42.2	1224	0.421	alive
21	esp32-01	2026-06-26 00:28:59+00	-1	37.2	20	0.421	alive
22	esp32-01	2026-06-26 00:41:27+00	-1	35.2	20	0.421	alive
23	esp32-01	2026-06-26 00:42:16+00	-1	39.2	20	0.421	alive
24	esp32-01	2026-06-26 00:44:39+00	-1	35.2	23	0.421	alive
25	esp32-01	2026-06-26 00:45:01+00	-1	37.2	20	0.421	alive
26	esp32-01	2026-06-26 00:45:26+00	-1	36.2	21	0.421	alive
27	esp32-01	2026-06-26 00:45:50+00	-1	41.2	21	0.421	alive
28	esp32-01	2026-06-26 00:46:17+00	-1	36.2	21	0.421	alive
29	esp32-01	2026-06-26 00:53:18+00	-1	33.2	20	0.663	alive
30	esp32-01	2026-06-26 00:54:27+00	-1	34.2	21	0.663	alive
31	esp32-01	2026-06-26 00:56:05+00	-1	35.2	25	0.39	alive
32	esp32-01	2026-06-26 01:02:49+00	-1	34.2	27	0.39	alive
33	esp32-01	2026-06-26 01:05:00+00	-1	32.2	26	0.39	alive
34	esp32-01	2026-06-26 01:08:02+00	-1	31.2	21	0.39	alive
35	esp32-01	2026-06-26 01:09:02+00	-1	33.2	20	0.39	alive
36	esp32-01	2026-06-26 01:11:39+00	-1	33.2	23	0.648	alive
37	esp32-01	2026-06-26 01:13:19+00	-1	35.2	24	0.648	alive
38	esp32-01	2026-06-26 01:15:15+00	-1	33.2	21	0.39	alive
39	esp32-01	2026-06-26 01:32:38+00	-1	26.2	20	0.39	alive
40	esp32-01	2026-06-26 01:36:39+00	-1	32.2	21	0.39	alive
41	esp32-01	2026-06-26 01:37:30+00	-1	34.2	73	0.39	alive
42	esp32-01	2026-06-26 01:37:59+00	-1	34.2	102	0.39	alive
43	esp32-01	2026-06-26 01:39:05+00	-1	34.2	168	0.359	alive
44	esp32-01	2026-06-26 01:39:57+00	-1	33.2	26	0.359	alive
45	esp32-01	2026-06-26 01:40:08+00	-1	35.2	37	0.359	alive
46	esp32-01	2026-06-26 01:42:00+00	-1	34.2	149	0.405	alive
47	esp32-01	2026-06-26 01:42:52+00	-1	34.2	20	0.405	alive
48	esp32-01	2026-06-26 01:45:23+00	-1	32.2	22	0.405	alive
49	esp32-01	2026-06-26 01:45:24+00	-1	34.2	22	0.405	alive
50	esp32-01	2026-06-26 01:45:47+00	-1	35.2	20	0.405	alive
51	esp32-01	2026-06-26 01:46:13+00	-1	36.2	20	0.405	alive
52	esp32-01	2026-06-26 01:46:39+00	-1	39.2	21	0.405	alive
53	esp32-01	2026-06-26 01:47:05+00	-1	36.2	20	0.405	alive
54	esp32-01	2026-06-26 01:47:29+00	-1	39.2	20	0.405	alive
55	esp32-01	2026-06-26 01:47:55+00	-1	36.2	20	0.405	alive
56	esp32-01	2026-06-26 01:47:56+00	-1	38.2	21	0.405	alive
57	esp32-01	2026-06-26 01:48:18+00	-1	42.2	19	0.405	alive
58	esp32-01	2026-06-26 01:48:43+00	-1	37.2	20	0.405	alive
59	esp32-01	2026-06-26 01:49:06+00	-1	42.2	18	0.405	alive
60	esp32-01	2026-06-26 01:49:33+00	-1	40.2	21	0.405	alive
61	esp32-01	2026-06-26 01:50:00+00	-1	42.2	21	0.405	alive
62	esp32-01	2026-06-26 01:50:26+00	-1	39.2	20	0.405	alive
63	esp32-01	2026-06-26 01:50:49+00	-1	38.2	19	0.405	alive
64	esp32-01	2026-06-26 01:51:14+00	-1	39.2	20	0.405	alive
65	esp32-01	2026-06-26 01:51:39+00	-1	39.2	20	0.405	alive
66	esp32-01	2026-06-26 01:52:03+00	-1	40.2	20	0.405	alive
67	esp32-01	2026-06-26 01:52:30+00	-1	44.2	22	0.405	alive
68	esp32-01	2026-06-26 01:53:04+00	-1	41.2	28	0.405	alive
69	esp32-01	2026-06-26 01:53:31+00	-1	44.2	21	0.405	alive
70	esp32-01	2026-06-26 01:53:57+00	-1	41.2	20	0.405	alive
71	esp32-01	2026-06-26 01:54:23+00	-1	42.2	20	0.405	alive
72	esp32-01	2026-06-26 01:57:59+00	-1	34.2	22	0.405	alive
73	esp32-01	2026-06-26 01:58:27+00	-1	40.2	24	0.405	alive
74	esp32-01	2026-06-26 01:58:53+00	-1	41.2	20	0.405	alive
75	esp32-01	2026-06-26 01:59:19+00	-1	41.2	20	0.405	alive
76	esp32-01	2026-06-26 01:59:51+00	-1	42.2	26	0.405	alive
77	esp32-01	2026-06-26 02:00:17+00	-1	38.2	20	0.405	alive
78	esp32-01	2026-06-26 02:00:46+00	-1	43.2	24	0.405	alive
79	esp32-01	2026-06-26 02:01:12+00	-1	43.2	21	0.405	alive
80	esp32-01	2026-06-26 02:01:38+00	-1	39.2	20	0.405	alive
81	esp32-01	2026-06-26 02:02:08+00	-1	42.2	25	0.405	alive
82	esp32-01	2026-06-26 02:02:52+00	-1	42.2	38	0.405	alive
83	esp32-01	2026-06-26 02:02:55+00	-1	40.2	41	0.405	alive
84	esp32-01	2026-06-26 02:03:50+00	-1	43.2	32	0.405	alive
85	esp32-01	2026-06-26 02:04:17+00	-1	43.2	21	0.405	alive
86	esp32-01	2026-06-26 02:04:43+00	-1	39.2	20	0.405	alive
87	esp32-01	2026-06-26 02:05:07+00	-1	40.2	20	0.405	alive
88	esp32-01	2026-06-26 02:05:19+00	-1	40.2	6	0.405	alive
89	esp32-01	2026-06-26 02:06:30+00	-1	37.2	21	0.405	alive
90	esp32-01	2026-06-26 02:06:36+00	-1	38.2	27	0.405	alive
91	esp32-01	2026-06-26 02:07:39+00	-1	36.2	90	0.292	alive
92	esp32-01	2026-06-26 02:09:42+00	-1	35.2	20	0.292	alive
93	esp32-01	2026-06-26 02:10:32+00	-1	36.2	20	0.292	alive
94	esp32-01	2026-06-26 02:12:48+00	-1	36.2	20	0.292	alive
95	esp32-01	2026-06-27 16:45:24+00	-1	34.2	20	0.292	alive
96	esp32-01	2026-06-27 16:47:29+00	-1	34.2	17	0.112	alive
97	esp32-01	2026-06-27 16:48:09+00	-1	34.2	21	0.112	alive
98	esp32-01	2026-06-27 16:49:15+00	-1	34.2	24	0.112	alive
99	esp32-01	2026-06-27 16:50:27+00	-1	34.2	19	0.112	alive
100	esp32-01	2026-06-27 16:51:11+00	-1	34.2	22	0.112	alive
101	esp32-01	2026-06-27 16:52:34+00	-1	34.2	21	0.112	alive
102	esp32-01	2026-06-27 16:53:01+00	-1	34.2	24	0.112	alive
103	esp32-01	2026-06-27 16:54:01+00	-1	34.2	23	0.112	alive
104	esp32-01	2026-06-27 16:55:26+00	-1	34.2	18	0.112	alive
105	esp32-01	2026-06-27 16:57:13+00	-1	34.2	17	0.202	alive
106	esp32-01	2026-06-27 17:00:15+00	-1	34.2	26	0.202	alive
107	esp32-01	2026-06-27 17:01:51+00	-1	35.2	17	0.202	alive
108	esp32-01	2026-06-27 17:02:32+00	-1	35.2	18	0.202	alive
109	esp32-01	2026-06-27 17:03:27+00	-1	35.2	19	0.202	alive
110	esp32-01	2026-06-27 17:04:39+00	-1	35.2	22	0.202	alive
111	esp32-01	2026-06-27 17:05:44+00	-1	35.2	23	0.202	alive
112	esp32-01	2026-06-27 17:07:47+00	-1	35.2	24	0.202	alive
113	esp32-01	2026-06-27 17:08:46+00	-1	35.2	17	0.202	alive
114	esp32-01	2026-06-27 17:09:17+00	-1	35.2	17	0.202	alive
115	esp32-01	2026-06-27 17:14:36+00	-1	45.2	131	0.202	alive
116	esp32-01	2026-06-27 17:16:03+00	-1	46.2	23	0.202	alive
117	esp32-01	2026-06-27 17:16:29+00	-1	46.2	20	0.202	alive
118	esp32-01	2026-06-27 17:17:18+00	-1	46.2	20	0.202	alive
119	esp32-01	2026-06-27 19:52:15+00	-1	32.2	20	0.202	alive
120	esp32-01	2026-06-27 19:53:27+00	-1	39.2	22	0.202	alive
121	esp32-01	2026-06-27 19:53:56+00	-1	40.2	23	0.202	alive
122	esp32-01	2026-06-27 19:54:23+00	-1	39.2	20	0.202	alive
123	esp32-01	2026-06-27 19:55:07+00	-1	42.2	20	0.202	alive
124	esp32-01	2026-06-27 19:55:33+00	-1	41.2	20	0.202	alive
125	esp32-01	2026-06-27 19:57:43+00	-1	43.2	20	0.202	alive
126	esp32-01	2026-06-27 19:59:19+00	-1	44.2	20	0.202	alive
127	esp32-01	2026-06-27 20:00:00+00	-1	46.2	24	0.202	alive
128	esp32-01	2026-06-27 20:00:26+00	-1	45.2	20	0.202	alive
129	esp32-01	2026-06-27 20:01:51+00	-1	45.2	20	0.202	alive
130	esp32-01	2026-06-27 20:03:03+00	-1	46.2	20	0.202	alive
131	esp32-01	2026-06-27 20:04:41+00	-1	47.2	26	0.202	alive
132	esp32-01	2026-06-27 20:05:07+00	-1	46.2	20	0.202	alive
133	esp32-01	2026-06-27 20:06:09+00	-1	47.2	21	0.202	alive
134	esp32-01	2026-06-27 20:06:36+00	-1	47.2	20	0.202	alive
135	esp32-01	2026-06-27 20:10:46+00	-1	47.2	20	0.202	alive
136	esp32-01	2026-06-27 20:12:31+00	-1	48.2	20	0.202	alive
137	esp32-01	2026-06-27 20:13:09+00	-1	48.2	20	0.202	alive
138	esp32-01	2026-06-27 20:15:53+00	-1	48.2	20	0.202	alive
139	esp32-01	2026-06-27 20:16:11+00	-1	48.2	38	0.202	alive
140	esp32-01	2026-06-27 20:16:51+00	-1	48.2	20	0.202	alive
141	esp32-01	2026-06-27 20:17:39+00	-1	49.2	22	0.202	alive
142	esp32-01	2026-06-27 20:18:05+00	-1	48.2	20	0.202	alive
143	esp32-01	2026-06-27 20:19:44+00	-1	49.2	21	0.202	alive
144	esp32-01	2026-06-27 20:20:10+00	-1	49.2	20	0.202	alive
145	esp32-01	2026-06-27 20:20:20+00	-1	48.2	30	0.202	alive
146	esp32-01	2026-06-27 20:23:09+00	-1	49.2	25	0.12	alive
147	esp32-01	2026-06-27 20:23:35+00	-1	48.2	20	0.12	alive
148	esp32-01	2026-06-27 20:24:42+00	-1	49.2	26	0.12	alive
149	esp32-01	2026-06-27 20:25:08+00	-1	49.2	20	0.12	alive
150	esp32-01	2026-06-27 20:25:35+00	-1	49.2	20	0.12	alive
151	esp32-01	2026-06-27 20:26:00+00	-1	49.2	20	0.12	alive
152	esp32-01	2026-06-27 20:26:49+00	-1	49.2	27	0.12	alive
153	esp32-01	2026-06-27 20:27:17+00	-1	49.2	21	0.12	alive
154	esp32-01	2026-06-27 20:27:40+00	-1	49.2	20	0.12	alive
155	esp32-01	2026-06-27 20:28:05+00	-1	49.2	20	0.12	alive
156	esp32-01	2026-06-27 20:28:34+00	-1	49.2	23	0.12	alive
157	esp32-01	2026-06-27 20:29:00+00	-1	48.2	20	0.12	alive
158	esp32-01	2026-06-27 20:31:21+00	-1	49.2	28	0.12	alive
159	esp32-01	2026-06-27 20:31:48+00	-1	49.2	21	0.12	alive
160	esp32-01	2026-06-27 20:32:30+00	-1	49.2	20	0.12	alive
161	esp32-01	2026-06-27 20:33:43+00	-1	49.2	20	0.12	alive
162	esp32-01	2026-06-27 20:34:23+00	-1	49.2	19	0.12	alive
163	esp32-01	2026-06-27 20:34:48+00	-1	49.2	19	0.12	alive
164	esp32-01	2026-06-27 20:35:14+00	-1	49.2	20	0.12	alive
165	esp32-01	2026-06-27 20:35:54+00	-1	49.2	20	0.12	alive
166	esp32-01	2026-06-27 20:36:34+00	-1	49.2	21	0.12	alive
167	esp32-01	2026-06-27 20:37:02+00	-1	49.2	22	0.12	alive
168	esp32-01	2026-06-27 20:37:29+00	-1	49.2	21	0.12	alive
169	esp32-01	2026-06-27 20:37:53+00	-1	49.2	20	0.12	alive
170	esp32-01	2026-06-27 20:38:19+00	-1	49.2	22	0.12	alive
171	esp32-01	2026-06-27 20:38:45+00	-1	49.2	20	0.12	alive
172	esp32-01	2026-06-27 20:39:11+00	-1	49.2	20	0.12	alive
173	esp32-01	2026-06-27 20:39:37+00	-1	49.2	22	0.12	alive
174	esp32-01	2026-06-27 20:40:04+00	-1	49.2	20	0.12	alive
175	esp32-01	2026-06-27 20:40:44+00	-1	49.2	20	0.12	alive
176	esp32-01	2026-06-27 20:41:48+00	-1	49.2	20	0.12	alive
177	esp32-01	2026-06-27 20:42:35+00	-1	49.2	20	0.12	alive
178	esp32-01	2026-06-27 20:43:06+00	-1	49.2	25	0.12	alive
179	esp32-01	2026-06-27 20:43:32+00	-1	49.2	20	0.12	alive
180	esp32-01	2026-06-27 20:43:58+00	-1	49.2	21	0.12	alive
181	esp32-01	2026-06-27 20:44:24+00	-1	49.2	20	0.12	alive
182	esp32-01	2026-06-27 20:44:49+00	-1	49.2	20	0.12	alive
183	esp32-01	2026-06-27 20:45:55+00	-1	49.2	20	0.12	alive
184	esp32-01	2026-06-27 20:47:14+00	-1	49.2	20	0.12	alive
185	esp32-01	2026-06-27 20:47:56+00	-1	49.2	20	0.12	alive
186	esp32-01	2026-06-27 20:48:20+00	-1	50.2	20	0.12	alive
187	esp32-01	2026-06-27 20:48:47+00	-1	49.2	20	0.12	alive
188	esp32-01	2026-06-27 20:49:30+00	-1	49.2	20	0.12	alive
189	esp32-01	2026-06-27 20:49:54+00	-1	47.2	20	0.12	alive
190	esp32-01	2026-06-27 20:50:32+00	-1	47.2	20	0.12	alive
191	esp32-01	2026-06-27 20:51:16+00	-1	49.2	20	0.12	alive
192	esp32-01	2026-06-27 20:51:42+00	-1	49.2	22	0.12	alive
193	esp32-01	2026-06-27 20:53:15+00	-1	49.2	26	0.12	alive
194	esp32-01	2026-06-27 20:53:49+00	-1	49.2	28	0.12	alive
195	esp32-01	2026-06-27 20:54:15+00	-1	49.2	20	0.12	alive
196	esp32-01	2026-06-27 20:54:41+00	-1	49.2	20	0.12	alive
197	esp32-01	2026-06-27 20:55:05+00	-1	49.2	20	0.12	alive
198	esp32-01	2026-06-27 20:56:18+00	-1	49.2	20	0.12	alive
199	esp32-01	2026-06-27 20:57:13+00	-1	49.2	24	0.12	alive
200	esp32-01	2026-06-27 20:57:45+00	-1	49.2	25	0.12	alive
201	esp32-01	2026-06-27 20:58:11+00	-1	49.2	20	0.12	alive
202	esp32-01	2026-06-27 20:59:56+00	-1	49.2	21	0.12	alive
203	esp32-01	2026-06-27 21:01:12+00	-1	47.2	24	0.12	alive
204	esp32-01	2026-06-27 21:01:40+00	-1	47.2	21	0.12	alive
205	esp32-01	2026-06-27 21:02:03+00	-1	48.2	20	0.12	alive
206	esp32-01	2026-06-27 21:02:35+00	-1	49.2	25	0.12	alive
207	esp32-01	2026-06-27 21:03:01+00	-1	48.2	20	0.12	alive
208	esp32-01	2026-06-27 21:03:49+00	-1	48.2	20	0.12	alive
209	esp32-01	2026-06-27 21:05:11+00	-1	48.2	22	0.12	alive
210	esp32-01	2026-06-27 21:05:49+00	-1	49.2	20	0.12	alive
211	esp32-01	2026-06-27 21:06:36+00	-1	49.2	20	0.12	alive
212	esp32-01	2026-06-27 21:07:01+00	-1	49.2	21	0.12	alive
213	esp32-01	2026-06-27 21:07:28+00	-1	49.2	21	0.12	alive
214	esp32-01	2026-06-27 21:07:55+00	-1	47.2	20	0.12	alive
215	esp32-01	2026-06-27 21:08:36+00	-1	48.2	24	0.12	alive
216	esp32-01	2026-06-27 21:09:15+00	-1	49.2	22	0.12	alive
217	esp32-01	2026-06-27 21:09:41+00	-1	49.2	20	0.12	alive
218	esp32-01	2026-06-27 21:19:05+00	-1	41.2	35	0.12	alive
219	esp32-01	2026-06-27 21:19:58+00	-1	43.2	28	0.12	alive
220	esp32-01	2026-06-27 21:29:58+00	-1	48.2	628	0.741	alive
221	esp32-01	2026-06-27 21:33:29+00	-1	47.2	26	0.741	alive
222	esp32-01	2026-06-27 21:34:29+00	-1	48.2	20	0.741	alive
223	esp32-01	2026-06-27 21:44:29+00	-1	49.2	620	0.175	alive
224	esp32-01	2026-06-27 21:47:36+00	-1	49.2	24	0.175	alive
225	esp32-01	2026-06-27 21:48:14+00	-1	49.2	19	0.175	alive
226	esp32-01	2026-06-27 21:54:03+00	-1	49.2	24	0.359	alive
227	esp32-01	2026-06-27 21:55:27+00	-1	49.2	32	0.347	alive
228	esp32-01	2026-06-27 22:03:37+00	-1	50.2	20	0.269	alive
229	esp32-01	2026-06-27 22:12:40+00	-1	49.2	19	0.484	alive
230	esp32-01	2026-06-27 22:17:05+00	-1	51.2	285	0.484	alive
231	esp32-01	2026-06-27 22:18:55+00	-1	46.2	22	0.484	alive
232	esp32-01	2026-06-27 22:20:36+00	-1	49.2	19	0.331	alive
233	esp32-01	2026-06-27 22:22:08+00	-1	49.2	19	0.331	alive
234	esp32-01	2026-06-27 22:22:49+00	-1	48.2	20	0.331	alive
235	esp32-01	2026-06-27 22:29:32+00	-1	49.2	19	0.331	alive
236	esp32-01	2026-06-27 22:32:37+00	-1	47.2	22	0.331	alive
237	esp32-01	2026-06-27 22:42:41+00	-1	50.2	626	0.331	alive
238	esp32-01	2026-06-27 22:48:30+00	-1	48.2	19	0.331	alive
239	esp32-01	2026-06-27 22:58:30+00	-1	48.2	619	0.331	alive
240	esp32-01	2026-06-27 23:01:40+00	-1	48.2	26	0.331	alive
241	esp32-01	2026-06-27 23:11:44+00	-1	51.2	630	0.331	alive
242	esp32-01	2026-06-27 23:15:50+00	-1	48.2	21	0.331	alive
243	esp32-01	2026-06-27 23:25:50+00	-1	48.2	621	0.331	alive
244	esp32-01	2026-06-27 23:33:59+00	-1	50.2	28	0.331	alive
245	esp32-01	2026-06-27 23:36:08+00	-1	47.2	20	0.331	alive
246	esp32-01	2026-06-27 23:39:38+00	-1	49.2	231	0.331	alive
247	esp32-01	2026-06-27 23:39:49+00	-1	49.2	241	0.331	alive
248	esp32-01	2026-07-03 03:41:01+00	-1	42.1	345	0.45	alive
249	esp32-99	2026-07-03 04:06:04+00	-1	38	0	0.45	alive
250	esp32-99	2026-07-03 04:07:04+00	-1	42.9	60	0.45	alive
251	esp32-99	2026-07-03 04:08:04+00	-1	39.7	120	0.45	alive
252	esp32-99	2026-07-03 04:08:20+00	-1	43.4	136	0.45	alive
253	esp32-99	2026-07-03 04:09:04+00	-1	41.6	180	0.45	alive
254	esp32-99	2026-07-03 04:10:04+00	-1	38.4	240	0.45	alive
255	esp32-99	2026-07-03 04:11:04+00	-1	40.2	300	0.45	alive
256	esp32-99	2026-07-03 04:12:04+00	-1	43.1	360	0.45	alive
257	esp32-99	2026-07-03 04:13:04+00	-1	41.2	420	0.45	alive
258	esp32-99	2026-07-03 04:14:04+00	-1	38.7	480	0.45	alive
259	esp32-99	2026-07-03 04:15:04+00	-1	38.7	540	0.45	alive
260	esp32-99	2026-07-03 04:16:04+00	-1	39.9	600	0.45	alive
261	esp32-99	2026-07-03 04:17:04+00	-1	41	660	0.45	alive
262	esp32-99	2026-07-03 04:18:04+00	-1	38	720	0.45	alive
263	esp32-99	2026-07-03 04:19:05+00	-1	38.1	780	0.45	alive
264	esp32-99	2026-07-03 04:20:05+00	-1	38.6	840	0.45	alive
265	esp32-99	2026-07-03 04:21:05+00	-1	38.6	900	0.45	alive
266	esp32-99	2026-07-03 04:22:05+00	-1	38.8	960	0.45	alive
267	esp32-99	2026-07-03 04:23:05+00	-1	41.2	1020	0.45	alive
268	esp32-99	2026-07-03 04:24:05+00	-1	39.9	1081	0.45	alive
269	esp32-99	2026-07-03 04:25:05+00	-1	41.8	1141	0.45	alive
270	esp32-99	2026-07-03 04:26:05+00	-1	38.3	1201	0.45	alive
\.


--
-- Data for Name: node_sensors; Type: TABLE DATA; Schema: public; Owner: iot
--

COPY public.node_sensors (id, node_id, sensor, installed) FROM stdin;
1	esp32-01	temp_ds18b20	t
2	esp32-01	turbidez	t
3	esp32-01	gps	t
4	esp32-01	audio	t
9	esp32-99	temp_ds18b20	t
10	esp32-99	turbidez	t
11	esp32-99	gps	t
12	esp32-99	audio	t
13	esp32-99	humedad	t
14	esp32-99	ph	t
15	esp32-99	nivel_agua	t
\.


--
-- Data for Name: node_status_history; Type: TABLE DATA; Schema: public; Owner: iot
--

COPY public.node_status_history (id, node_id, ts, old_status, new_status) FROM stdin;
2	esp32-01	2026-06-25 23:27:24+00	UNKNOWN	ONLINE
3	esp32-01	2026-06-27 16:30:09+00	ONLINE	COMPROMISED
4	esp32-01	2026-06-27 16:45:24+00	COMPROMISED	ONLINE
5	esp32-01	2026-06-27 18:14:26+00	ONLINE	OFFLINE
6	esp32-01	2026-06-27 19:52:15+00	OFFLINE	ONLINE
7	esp32-01	2026-07-03 02:48:20+00	ONLINE	COMPROMISED
8	esp32-01	2026-07-03 03:41:01.819655+00	COMPROMISED	ONLINE
9	esp32-99	2026-07-03 04:06:04.861569+00	UNKNOWN	ONLINE
10	esp32-01	2026-07-03 04:12:11.672169+00	ONLINE	OFFLINE
11	esp32-99	2026-07-03 17:09:48.525914+00	ONLINE	OFFLINE
\.


--
-- Data for Name: nodes; Type: TABLE DATA; Schema: public; Owner: iot
--

COPY public.nodes (node_id, node_name, district, lat, lon, alt, status, battery_pct, chip_temp_c, threshold, uptime_s, first_seen, last_seen, last_heartbeat, last_reading, is_simulated, risk_level, risk_score) FROM stdin;
esp32-01	Nodo SJL-01	San Juan de Lurigancho	-11.9615	-77.0012	152	OFFLINE	-1	42.1	0.45	345	2026-06-25 05:07:24+00	2026-07-03 17:28:31.582625+00	2026-07-03 03:41:01+00	2026-07-03 03:41:01.810653+00	f	alto	63.5
esp32-99	\N	\N	-12.020045	-76.994719	150	OFFLINE	-1	38.3	0.45	1201	2026-07-03 04:06:04.856362+00	2026-07-03 17:28:00.538141+00	2026-07-03 04:26:05+00	2026-07-03 04:26:05.99482+00	t	critico	95
\.


--
-- Data for Name: sensor_readings; Type: TABLE DATA; Schema: public; Owner: iot
--

COPY public.sensor_readings (id, node_id, ts, temp_c, turb_raw, turb_v, humedad, ph, nivel_agua, audio_conf, extra) FROM stdin;
2	esp32-01	2026-07-03 03:41:01.810653+00	27.4	1800	1.45	\N	\N	\N	\N	\N
3	esp32-99	2026-07-03 04:06:07.891441+00	28	2978	2.4	75	\N	\N	\N	\N
4	esp32-99	2026-07-03 04:06:34.858919+00	28	2978	2.4	75	\N	\N	0.9	\N
5	esp32-99	2026-07-03 04:07:04.906578+00	28	2978	2.4	75	\N	\N	0.9	\N
6	esp32-99	2026-07-03 04:07:34.870052+00	28	2978	2.4	75	\N	\N	0.9	\N
7	esp32-99	2026-07-03 04:07:45.811608+00	28	2978	2.4	75	\N	\N	0.9	\N
8	esp32-99	2026-07-03 04:08:04.883761+00	28	2978	2.4	75	\N	\N	0.9	\N
9	esp32-99	2026-07-03 04:08:22.903198+00	28	2978	2.4	75	\N	\N	0.9	\N
10	esp32-99	2026-07-03 04:08:34.879523+00	28	2978	2.4	75	\N	\N	0.9	\N
11	esp32-99	2026-07-03 04:09:04.927747+00	28	2978	2.4	75	\N	\N	0.9	\N
12	esp32-99	2026-07-03 04:09:34.891782+00	28	2978	2.4	75	\N	\N	0.9	\N
13	esp32-99	2026-07-03 04:10:04.938577+00	28	2978	2.4	75	\N	\N	0.9	\N
14	esp32-99	2026-07-03 04:10:34.901748+00	28	2978	2.4	75	\N	\N	0.9	\N
15	esp32-99	2026-07-03 04:11:04.949542+00	28	2978	2.4	75	\N	\N	0.9	\N
16	esp32-99	2026-07-03 04:11:34.913256+00	28	2978	2.4	75	\N	\N	0.9	\N
17	esp32-99	2026-07-03 04:12:04.962592+00	28	2978	2.4	75	\N	\N	0.9	\N
18	esp32-99	2026-07-03 04:12:34.924612+00	28	2978	2.4	75	\N	\N	0.9	\N
19	esp32-99	2026-07-03 04:13:04.978498+00	28	2978	2.4	75	\N	\N	0.9	\N
20	esp32-99	2026-07-03 04:13:34.937684+00	28	2978	2.4	75	\N	\N	0.9	\N
21	esp32-99	2026-07-03 04:14:04.987137+00	28	2978	2.4	75	\N	\N	0.9	\N
22	esp32-99	2026-07-03 04:14:34.94821+00	28	2978	2.4	75	\N	\N	0.9	\N
23	esp32-99	2026-07-03 04:15:04.994703+00	28	2978	2.4	75	\N	\N	0.9	\N
24	esp32-99	2026-07-03 04:15:34.958206+00	28	2978	2.4	75	\N	\N	0.9	\N
25	esp32-99	2026-07-03 04:16:05.006578+00	28	2978	2.4	75	\N	\N	0.9	\N
26	esp32-99	2026-07-03 04:16:34.97113+00	28	2978	2.4	75	\N	\N	0.9	\N
27	esp32-99	2026-07-03 04:17:05.022807+00	28	2978	2.4	75	\N	\N	0.9	\N
28	esp32-99	2026-07-03 04:17:34.985752+00	28	2978	2.4	75	\N	\N	0.9	\N
29	esp32-99	2026-07-03 04:18:05.035117+00	28	2978	2.4	75	\N	\N	0.9	\N
30	esp32-99	2026-07-03 04:18:34.999901+00	28	2978	2.4	75	\N	\N	0.9	\N
31	esp32-99	2026-07-03 04:19:05.047917+00	28	2978	2.4	75	\N	\N	\N	\N
32	esp32-99	2026-07-03 04:19:35.011911+00	28	2978	2.4	75	\N	\N	0.9	\N
33	esp32-99	2026-07-03 04:20:05.061738+00	28	2978	2.4	75	\N	\N	0.9	\N
34	esp32-99	2026-07-03 04:20:35.025045+00	28	2978	2.4	75	\N	\N	0.9	\N
35	esp32-99	2026-07-03 04:21:05.074549+00	28	2978	2.4	75	\N	\N	0.9	\N
36	esp32-99	2026-07-03 04:21:35.038567+00	28	2978	2.4	75	\N	\N	0.9	\N
37	esp32-99	2026-07-03 04:22:05.08694+00	28	2978	2.4	75	\N	\N	0.9	\N
38	esp32-99	2026-07-03 04:22:35.049714+00	28	2978	2.4	75	\N	\N	0.9	\N
39	esp32-99	2026-07-03 04:23:05.095601+00	28	2978	2.4	75	\N	\N	0.9	\N
40	esp32-99	2026-07-03 04:23:35.061191+00	28	2978	2.4	75	\N	\N	0.9	\N
41	esp32-99	2026-07-03 04:24:05.962383+00	28	2978	2.4	75	\N	\N	0.9	\N
42	esp32-99	2026-07-03 04:24:35.926483+00	28	2978	2.4	75	\N	\N	0.9	\N
43	esp32-99	2026-07-03 04:25:05.983086+00	28	2978	2.4	75	\N	\N	0.9	\N
44	esp32-99	2026-07-03 04:25:35.936638+00	28	2978	2.4	75	\N	\N	0.9	\N
45	esp32-99	2026-07-03 04:26:05.99482+00	28	2978	2.4	75	\N	\N	0.9	\N
\.


--
-- Data for Name: system_config; Type: TABLE DATA; Schema: public; Owner: iot
--

COPY public.system_config (key, value, description, updated_at) FROM stdin;
risk	{"pesos": {"ph": 0.05, "temp": 0.3, "humedad": 0.2, "turbidez": 0.25, "actividad": 0.25, "nivel_agua": 0.05}, "ph_optimo": [6.5, 8.5], "temp_rango": [15, 40], "temp_optima": [25, 30], "turb_v_alta": 2.0, "turb_v_baja": 0.5, "actividad_max": 10, "humedad_rango": [30, 100], "humedad_optima": [60, 80], "turb_invertido": false, "umbrales_nivel": {"alto": 50, "medio": 25, "critico": 75}, "actividad_ventana_h": 72}	pesos y umbrales del motor de riesgo	2026-07-03 03:31:36.262045+00
\.


--
-- Data for Name: videos; Type: TABLE DATA; Schema: public; Owner: iot
--

COPY public.videos (id, node_id, received_at, file_path, file_size_kb) FROM stdin;
1	esp32-01	2026-06-24 17:58:36+00	clips/esp32-01/20260624-125828.webm	4715
2	esp32-01	2026-06-24 23:11:03+00	clips/esp32-01/20260624-181101.webm	990
3	esp32-01	2026-06-23 23:52:16+00	clips/esp32-01/20260623-184416.webm	4445
4	esp32-01	2026-06-24 23:57:42+00	clips/esp32-01/20260624-185740.webm	919
5	esp32-01	2026-06-24 22:59:55+00	clips/esp32-01/20260624-175954.webm	737
6	esp32-01	2026-06-23 23:54:55+00	clips/esp32-01/20260623-185447.webm	4228
7	esp32-01	2026-06-25 00:43:07+00	clips/esp32-01/20260624-194306.webm	595
8	esp32-01	2026-06-24 00:19:38+00	clips/esp32-01/20260623-191930.webm	6486
9	esp32-01	2026-06-24 17:58:57+00	clips/esp32-01/20260624-125848.webm	4987
10	esp32-01	2026-06-24 23:25:47+00	clips/esp32-01/20260624-182546.webm	961
11	esp32-01	2026-06-24 17:26:02+00	clips/esp32-01/20260624-122554.webm	4672
12	esp32-01	2026-06-23 23:51:58+00	clips/esp32-01/20260623-183109.webm	5766
13	esp32-01	2026-06-24 23:32:47+00	clips/esp32-01/20260624-183246.webm	891
14	esp32-01	2026-06-24 18:11:50+00	clips/esp32-01/20260624-131142.webm	4926
15	esp32-01	2026-06-23 23:52:23+00	clips/esp32-01/20260623-184443.webm	3143
16	esp32-01	2026-06-24 23:10:41+00	clips/esp32-01/20260624-181039.webm	989
17	esp32-01	2026-06-24 22:28:27+00	clips/esp32-01/20260624-172826.webm	714
18	esp32-01	2026-06-24 22:02:26+00	clips/esp32-01/20260624-170224.webm	733
19	esp32-01	2026-06-24 18:43:16+00	clips/esp32-01/20260624-134308.webm	3889
20	esp32-01	2026-06-24 23:00:28+00	clips/esp32-01/20260624-180025.webm	2078
21	esp32-01	2026-06-24 18:30:56+00	clips/esp32-01/20260624-133048.webm	3697
22	esp32-01	2026-06-24 23:31:25+00	clips/esp32-01/20260624-183124.webm	711
23	esp32-01	2026-06-24 22:43:13+00	clips/esp32-01/20260624-174312.webm	938
24	esp32-01	2026-06-23 23:52:07+00	clips/esp32-01/20260623-183636.webm	4468
25	esp32-01	2026-06-24 23:33:17+00	clips/esp32-01/20260624-183317.webm	591
26	esp32-01	2026-06-24 18:06:06+00	clips/esp32-01/20260624-130558.webm	3454
27	esp32-01	2026-06-24 23:51:28+00	clips/esp32-01/20260624-185126.webm	1084
28	esp32-01	2026-06-24 22:59:11+00	clips/esp32-01/20260624-175910.webm	1086
29	esp32-01	2026-06-24 23:11:24+00	clips/esp32-01/20260624-181122.webm	1011
30	esp32-01	2026-06-23 23:51:47+00	clips/esp32-01/20260623-182106.webm	4117
31	esp32-01	2026-06-25 00:21:56+00	clips/esp32-01/20260624-192154.webm	1076
32	esp32-01	2026-06-24 18:06:16+00	clips/esp32-01/20260624-130608.webm	4624
33	esp32-01	2026-06-24 23:39:35+00	clips/esp32-01/20260624-183934.webm	1058
34	esp32-01	2026-06-24 18:12:11+00	clips/esp32-01/20260624-131203.webm	3817
35	esp32-01	2026-06-24 18:43:31+00	clips/esp32-01/20260624-134322.webm	3931
36	esp32-01	2026-06-24 22:27:05+00	clips/esp32-01/20260624-172704.webm	233
37	esp32-01	2026-06-24 18:11:30+00	clips/esp32-01/20260624-131122.webm	3423
38	esp32-01	2026-06-24 17:59:08+00	clips/esp32-01/20260624-125859.webm	5023
39	esp32-01	2026-06-23 23:51:38+00	clips/esp32-01/20260623-175544.webm	3663
40	esp32-01	2026-06-23 23:52:40+00	clips/esp32-01/20260623-184606.webm	4483
41	esp32-01	2026-06-24 18:11:10+00	clips/esp32-01/20260624-131101.webm	3647
42	esp32-01	2026-06-24 17:58:46+00	clips/esp32-01/20260624-125838.webm	4958
43	esp32-01	2026-06-23 23:59:19+00	clips/esp32-01/20260623-185911.webm	4153
44	esp32-01	2026-06-24 19:29:44+00	clips/esp32-01/20260624-142942.webm	1334
45	esp32-01	2026-06-24 18:35:34+00	clips/esp32-01/20260624-133526.webm	4140
46	esp32-01	2026-06-25 00:54:47+00	clips/esp32-01/20260624-195445.webm	1359
47	esp32-01	2026-06-24 22:08:19+00	clips/esp32-01/20260624-170817.webm	963
48	esp32-01	2026-06-24 18:48:45+00	clips/esp32-01/20260624-134842.webm	1321
49	esp32-01	2026-06-24 00:01:16+00	clips/esp32-01/20260623-190108.webm	4100
50	esp32-01	2026-06-24 22:14:57+00	clips/esp32-01/20260624-171455.webm	1027
51	esp32-01	2026-06-24 22:58:24+00	clips/esp32-01/20260624-175824.webm	532
52	esp32-01	2026-06-24 18:44:51+00	clips/esp32-01/20260624-134443.webm	3873
53	esp32-01	2026-06-25 00:12:03+00	clips/esp32-01/20260624-191200.webm	980
54	esp32-01	2026-06-24 23:12:03+00	clips/esp32-01/20260624-181202.webm	668
55	esp32-01	2026-06-23 23:52:32+00	clips/esp32-01/20260623-184427.webm	4529
56	esp32-01	2026-06-24 17:58:25+00	clips/esp32-01/20260624-125816.webm	4061
57	esp32-01	2026-06-24 17:58:12+00	clips/esp32-01/20260624-125804.webm	4390
58	esp32-01	2026-06-24 17:59:18+00	clips/esp32-01/20260624-125910.webm	4866
59	esp32-01	2026-06-25 03:18:09+00	clips/esp32-01/20260624-221808.webm	685
60	esp32-01	2026-06-24 00:30:00+00	clips/esp32-01/20260623-192951.webm	6423
61	esp32-01	2026-06-24 18:12:31+00	clips/esp32-01/20260624-131223.webm	4230
62	esp32-01	2026-06-24 23:10:18+00	clips/esp32-01/20260624-181017.webm	269
63	esp32-01	2026-06-25 03:25:46+00	clips/esp32-01/20260624-222544.webm	974
64	esp32-01	2026-06-24 17:37:50+00	clips/esp32-01/20260624-123742.webm	4565
65	esp32-01	2026-06-24 22:58:49+00	clips/esp32-01/20260624-175847.webm	1425
66	esp32-01	2026-06-25 00:49:07+00	clips/esp32-01/20260624-194905.webm	1000
67	esp32-01	2026-06-25 22:57:30+00	clips/esp32-01/20260625-175721.webm	591
68	esp32-01	2026-06-26 00:28:34+00	clips/esp32-01/20260625-192832.webm	957
69	esp32-01	2026-06-26 00:41:51+00	clips/esp32-01/20260625-194150.webm	569
70	esp32-01	2026-06-26 00:44:36+00	clips/esp32-01/20260625-194435.webm	605
71	esp32-01	2026-06-26 00:45:01+00	clips/esp32-01/20260625-194459.webm	959
72	esp32-01	2026-06-26 00:45:24+00	clips/esp32-01/20260625-194523.webm	515
73	esp32-01	2026-06-26 00:45:51+00	clips/esp32-01/20260625-194550.webm	729
74	esp32-01	2026-06-26 00:56:02+00	clips/esp32-01/20260625-195600.webm	1012
75	esp32-01	2026-06-26 01:05:03+00	clips/esp32-01/20260625-200503.webm	156
76	esp32-01	2026-06-26 01:08:35+00	clips/esp32-01/20260625-200835.webm	98
77	esp32-01	2026-06-26 01:42:27+00	clips/esp32-01/20260625-204226.webm	619
78	esp32-01	2026-06-26 01:45:23+00	clips/esp32-01/20260625-204521.webm	911
79	esp32-01	2026-06-26 01:45:48+00	clips/esp32-01/20260625-204547.webm	753
80	esp32-01	2026-06-26 01:46:13+00	clips/esp32-01/20260625-204612.webm	654
81	esp32-01	2026-06-26 01:46:40+00	clips/esp32-01/20260625-204639.webm	617
82	esp32-01	2026-06-26 01:47:04+00	clips/esp32-01/20260625-204703.webm	543
83	esp32-01	2026-06-26 01:47:30+00	clips/esp32-01/20260625-204729.webm	654
84	esp32-01	2026-06-26 01:47:53+00	clips/esp32-01/20260625-204753.webm	420
85	esp32-01	2026-06-26 01:48:19+00	clips/esp32-01/20260625-204818.webm	760
86	esp32-01	2026-06-26 01:48:43+00	clips/esp32-01/20260625-204841.webm	841
87	esp32-01	2026-06-26 01:49:07+00	clips/esp32-01/20260625-204906.webm	828
88	esp32-01	2026-06-26 01:49:33+00	clips/esp32-01/20260625-204932.webm	371
89	esp32-01	2026-06-26 01:50:01+00	clips/esp32-01/20260625-205000.webm	684
90	esp32-01	2026-06-26 01:50:25+00	clips/esp32-01/20260625-205024.webm	683
91	esp32-01	2026-06-26 01:50:49+00	clips/esp32-01/20260625-205048.webm	702
92	esp32-01	2026-06-26 01:51:14+00	clips/esp32-01/20260625-205113.webm	591
93	esp32-01	2026-06-26 01:51:38+00	clips/esp32-01/20260625-205137.webm	741
94	esp32-01	2026-06-26 01:52:03+00	clips/esp32-01/20260625-205202.webm	632
95	esp32-01	2026-06-26 01:52:31+00	clips/esp32-01/20260625-205230.webm	671
96	esp32-01	2026-06-26 01:53:03+00	clips/esp32-01/20260625-205302.webm	877
97	esp32-01	2026-06-26 01:53:58+00	clips/esp32-01/20260625-205357.webm	837
98	esp32-01	2026-06-26 01:53:32+00	clips/esp32-01/20260625-205331.webm	861
99	esp32-01	2026-06-26 01:54:23+00	clips/esp32-01/20260625-205422.webm	896
100	esp32-01	2026-06-26 01:57:57+00	clips/esp32-01/20260625-205757.webm	636
101	esp32-01	2026-06-26 01:58:28+00	clips/esp32-01/20260625-205827.webm	781
102	esp32-01	2026-06-26 01:58:54+00	clips/esp32-01/20260625-205853.webm	1032
103	esp32-01	2026-06-26 01:59:20+00	clips/esp32-01/20260625-205919.webm	898
104	esp32-01	2026-06-26 01:59:52+00	clips/esp32-01/20260625-205951.webm	793
105	esp32-01	2026-06-26 02:00:16+00	clips/esp32-01/20260625-210015.webm	550
106	esp32-01	2026-06-26 02:00:47+00	clips/esp32-01/20260625-210046.webm	707
107	esp32-01	2026-06-26 02:01:14+00	clips/esp32-01/20260625-210112.webm	830
108	esp32-01	2026-06-26 02:01:38+00	clips/esp32-01/20260625-210137.webm	574
109	esp32-01	2026-06-26 02:02:09+00	clips/esp32-01/20260625-210208.webm	475
110	esp32-01	2026-06-26 02:02:53+00	clips/esp32-01/20260625-210252.webm	511
111	esp32-01	2026-06-26 02:03:51+00	clips/esp32-01/20260625-210350.webm	734
112	esp32-01	2026-06-26 02:04:18+00	clips/esp32-01/20260625-210417.webm	922
113	esp32-01	2026-06-26 02:04:42+00	clips/esp32-01/20260625-210441.webm	756
114	esp32-01	2026-06-26 02:05:08+00	clips/esp32-01/20260625-210507.webm	744
115	esp32-01	2026-06-26 02:05:34+00	clips/esp32-01/20260625-210533.webm	799
116	esp32-01	2026-06-26 02:09:17+00	clips/esp32-01/20260625-210916.webm	824
117	esp32-01	2026-06-26 02:10:08+00	clips/esp32-01/20260625-211006.webm	693
118	esp32-01	2026-06-26 02:12:23+00	clips/esp32-01/20260625-211221.webm	839
119	esp32-01	2026-06-27 16:48:47+00	clips/esp32-01/20260627-114845.webm	968
120	esp32-01	2026-06-27 16:50:02+00	clips/esp32-01/20260627-115002.webm	1
121	esp32-01	2026-06-27 16:50:45+00	clips/esp32-01/20260627-115043.webm	1010
122	esp32-01	2026-06-27 16:51:30+00	clips/esp32-01/20260627-115129.webm	690
123	esp32-01	2026-06-27 16:52:32+00	clips/esp32-01/20260627-115231.webm	695
124	esp32-01	2026-06-27 16:53:33+00	clips/esp32-01/20260627-115332.webm	256
125	esp32-01	2026-06-27 16:56:52+00	clips/esp32-01/20260627-115650.webm	940
126	esp32-01	2026-06-27 16:58:20+00	clips/esp32-01/20260627-115819.webm	513
127	esp32-01	2026-06-27 17:01:29+00	clips/esp32-01/20260627-120128.webm	856
128	esp32-01	2026-06-27 17:02:09+00	clips/esp32-01/20260627-120207.webm	931
129	esp32-01	2026-06-27 17:03:03+00	clips/esp32-01/20260627-120303.webm	1
130	esp32-01	2026-06-27 17:04:13+00	clips/esp32-01/20260627-120411.webm	755
131	esp32-01	2026-06-27 17:05:16+00	clips/esp32-01/20260627-120514.webm	923
132	esp32-01	2026-06-27 17:07:19+00	clips/esp32-01/20260627-120717.webm	944
133	esp32-01	2026-06-27 17:08:24+00	clips/esp32-01/20260627-120823.webm	660
134	esp32-01	2026-06-27 17:08:56+00	clips/esp32-01/20260627-120854.webm	985
135	esp32-01	2026-06-27 17:09:50+00	clips/esp32-01/20260627-120949.webm	680
136	esp32-01	2026-06-27 17:15:36+00	clips/esp32-01/20260627-121534.webm	951
137	esp32-01	2026-06-27 17:16:03+00	clips/esp32-01/20260627-121603.webm	1
138	esp32-01	2026-06-27 21:47:37+00	clips/esp32-01/20260627-164736.webm	1023
139	esp32-01	2026-06-27 21:47:48+00	clips/esp32-01/20260627-164747.webm	930
140	esp32-01	2026-06-27 21:49:15+00	clips/esp32-01/20260627-164913.webm	996
141	esp32-01	2026-06-27 21:57:29+00	clips/esp32-01/20260627-165729.webm	1
142	esp32-01	2026-06-27 22:01:01+00	clips/esp32-01/20260627-170100.webm	963
143	esp32-01	2026-06-27 22:02:26+00	clips/esp32-01/20260627-170225.webm	1001
144	esp32-01	2026-06-27 22:02:48+00	clips/esp32-01/20260627-170247.webm	718
145	esp32-01	2026-06-27 22:02:38+00	clips/esp32-01/20260627-170237.webm	1113
146	esp32-01	2026-06-27 22:48:06+00	clips/esp32-01/20260627-174805.webm	870
147	esp32-01	2026-06-27 23:08:28+00	clips/esp32-01/20260627-180825.webm	1096
148	esp32-01	2026-06-27 23:08:37+00	clips/esp32-01/20260627-180834.webm	1157
149	esp32-01	2026-06-27 23:08:49+00	clips/esp32-01/20260627-180846.webm	1197
150	esp32-01	2026-06-27 23:09:07+00	clips/esp32-01/20260627-180905.webm	1051
151	esp32-01	2026-06-27 23:08:58+00	clips/esp32-01/20260627-180855.webm	954
152	esp32-01	2026-06-27 23:09:18+00	clips/esp32-01/20260627-180916.webm	1350
153	esp32-01	2026-06-27 23:09:39+00	clips/esp32-01/20260627-180937.webm	1283
154	esp32-01	2026-06-27 23:09:28+00	clips/esp32-01/20260627-180926.webm	933
155	esp32-01	2026-06-27 23:09:49+00	clips/esp32-01/20260627-180948.webm	914
156	esp32-01	2026-06-27 23:10:10+00	clips/esp32-01/20260627-181009.webm	859
157	esp32-01	2026-06-27 23:10:20+00	clips/esp32-01/20260627-181019.webm	574
158	esp32-01	2026-06-27 23:10:01+00	clips/esp32-01/20260627-180959.webm	1118
159	esp32-01	2026-06-27 23:10:50+00	clips/esp32-01/20260627-181048.webm	847
160	esp32-01	2026-06-27 23:10:31+00	clips/esp32-01/20260627-181030.webm	795
161	esp32-01	2026-06-27 23:11:33+00	clips/esp32-01/20260627-181131.webm	983
162	esp32-01	2026-06-27 23:11:45+00	clips/esp32-01/20260627-181144.webm	467
163	esp32-01	2026-06-27 23:12:15+00	clips/esp32-01/20260627-181214.webm	613
164	esp32-01	2026-06-27 23:12:31+00	clips/esp32-01/20260627-181229.webm	868
165	esp32-01	2026-06-27 23:13:07+00	clips/esp32-01/20260627-181306.webm	719
166	esp32-01	2026-06-27 23:13:50+00	clips/esp32-01/20260627-181350.webm	391
167	esp32-01	2026-06-27 23:13:40+00	clips/esp32-01/20260627-181339.webm	787
168	esp32-01	2026-06-27 23:13:28+00	clips/esp32-01/20260627-181327.webm	473
169	esp32-01	2026-06-27 23:14:01+00	clips/esp32-01/20260627-181359.webm	911
170	esp32-01	2026-06-27 23:14:23+00	clips/esp32-01/20260627-181422.webm	545
171	esp32-01	2026-06-27 23:14:14+00	clips/esp32-01/20260627-181413.webm	585
172	esp32-01	2026-06-27 23:14:44+00	clips/esp32-01/20260627-181443.webm	519
173	esp32-01	2026-06-27 23:14:35+00	clips/esp32-01/20260627-181433.webm	989
174	esp32-01	2026-06-27 23:15:09+00	clips/esp32-01/20260627-181506.webm	1104
175	esp32-01	2026-06-27 23:15:18+00	clips/esp32-01/20260627-181517.webm	530
176	esp32-01	2026-06-27 23:17:24+00	clips/esp32-01/20260627-181722.webm	993
177	esp32-01	2026-06-27 23:29:20+00	clips/esp32-01/20260627-182918.webm	989
178	esp32-01	2026-06-27 23:31:36+00	clips/esp32-01/20260627-183135.webm	438
179	esp32-01	2026-06-27 23:31:58+00	clips/esp32-01/20260627-183157.webm	807
180	esp32-01	2026-06-27 23:31:47+00	clips/esp32-01/20260627-183146.webm	936
181	esp32-01	2026-06-27 23:32:34+00	clips/esp32-01/20260627-183233.webm	574
182	esp32-01	2026-06-27 23:32:21+00	clips/esp32-01/20260627-183220.webm	667
183	esp32-01	2026-06-27 23:32:12+00	clips/esp32-01/20260627-183211.webm	916
184	esp32-01	2026-06-27 23:33:04+00	clips/esp32-01/20260627-183303.webm	811
185	esp32-01	2026-06-27 23:32:50+00	clips/esp32-01/20260627-183248.webm	1135
186	esp32-01	2026-06-27 23:33:59+00	clips/esp32-01/20260627-183359.webm	457
187	esp32-01	2026-06-27 23:34:11+00	clips/esp32-01/20260627-183410.webm	637
188	esp32-01	2026-06-27 23:34:33+00	clips/esp32-01/20260627-183432.webm	887
189	esp32-01	2026-06-27 23:34:22+00	clips/esp32-01/20260627-183421.webm	675
190	esp32-01	2026-06-27 23:34:44+00	clips/esp32-01/20260627-183442.webm	860
191	esp32-01	2026-06-27 23:34:56+00	clips/esp32-01/20260627-183454.webm	1318
192	esp32-01	2026-06-27 23:35:05+00	clips/esp32-01/20260627-183503.webm	988
193	esp32-01	2026-06-27 23:35:20+00	clips/esp32-01/20260627-183519.webm	1022
194	esp32-01	2026-06-27 23:35:31+00	clips/esp32-01/20260627-183529.webm	1271
195	esp32-01	2026-06-27 23:38:21+00	clips/esp32-01/20260627-183819.webm	1291
196	esp32-01	2026-06-27 23:40:35+00	clips/esp32-01/20260627-184033.webm	1084
197	esp32-01	2026-06-27 23:40:51+00	clips/esp32-01/20260627-184049.webm	800
198	esp32-01	2026-06-27 23:41:05+00	clips/esp32-01/20260627-184104.webm	540
199	esp32-01	2026-06-27 23:41:19+00	clips/esp32-01/20260627-184117.webm	864
399	esp32-01	2026-07-03 03:41:05+00	clips/esp32-01/20260702-224103.webm	2510
400	esp32-99	2026-07-03 04:06:10+00	clips/esp32-99/20260702-230608.webm	2519
401	esp32-99	2026-07-03 04:07:48+00	clips/esp32-99/20260702-230746.webm	2520
402	esp32-99	2026-07-03 04:08:25+00	clips/esp32-99/20260702-230823.webm	2503
\.


--
-- Name: alert_history_id_seq; Type: SEQUENCE SET; Schema: public; Owner: iot
--

SELECT pg_catalog.setval('public.alert_history_id_seq', 45, true);


--
-- Name: alerts_id_seq; Type: SEQUENCE SET; Schema: public; Owner: iot
--

SELECT pg_catalog.setval('public.alerts_id_seq', 33, true);


--
-- Name: anomalies_id_seq; Type: SEQUENCE SET; Schema: public; Owner: iot
--

SELECT pg_catalog.setval('public.anomalies_id_seq', 264, true);


--
-- Name: detections_id_seq; Type: SEQUENCE SET; Schema: public; Owner: iot
--

SELECT pg_catalog.setval('public.detections_id_seq', 344, true);


--
-- Name: events_id_seq; Type: SEQUENCE SET; Schema: public; Owner: iot
--

SELECT pg_catalog.setval('public.events_id_seq', 36, true);


--
-- Name: heartbeats_id_seq; Type: SEQUENCE SET; Schema: public; Owner: iot
--

SELECT pg_catalog.setval('public.heartbeats_id_seq', 270, true);


--
-- Name: node_sensors_id_seq; Type: SEQUENCE SET; Schema: public; Owner: iot
--

SELECT pg_catalog.setval('public.node_sensors_id_seq', 15, true);


--
-- Name: node_status_history_id_seq; Type: SEQUENCE SET; Schema: public; Owner: iot
--

SELECT pg_catalog.setval('public.node_status_history_id_seq', 11, true);


--
-- Name: sensor_readings_id_seq; Type: SEQUENCE SET; Schema: public; Owner: iot
--

SELECT pg_catalog.setval('public.sensor_readings_id_seq', 45, true);


--
-- Name: users_id_seq; Type: SEQUENCE SET; Schema: public; Owner: iot
--

SELECT pg_catalog.setval('public.users_id_seq', 2, true);


--
-- Name: videos_id_seq; Type: SEQUENCE SET; Schema: public; Owner: iot
--

SELECT pg_catalog.setval('public.videos_id_seq', 402, true);


--
-- Name: alert_history alert_history_pkey; Type: CONSTRAINT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.alert_history
    ADD CONSTRAINT alert_history_pkey PRIMARY KEY (id);


--
-- Name: alerts alerts_pkey; Type: CONSTRAINT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT alerts_pkey PRIMARY KEY (id);


--
-- Name: anomalies anomalies_pkey; Type: CONSTRAINT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.anomalies
    ADD CONSTRAINT anomalies_pkey PRIMARY KEY (id);


--
-- Name: detections detections_pkey; Type: CONSTRAINT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.detections
    ADD CONSTRAINT detections_pkey PRIMARY KEY (id);


--
-- Name: detector_params detector_params_pkey; Type: CONSTRAINT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.detector_params
    ADD CONSTRAINT detector_params_pkey PRIMARY KEY (key);


--
-- Name: events events_pkey; Type: CONSTRAINT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.events
    ADD CONSTRAINT events_pkey PRIMARY KEY (id);


--
-- Name: heartbeats heartbeats_pkey; Type: CONSTRAINT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.heartbeats
    ADD CONSTRAINT heartbeats_pkey PRIMARY KEY (id);


--
-- Name: node_sensors node_sensors_node_id_sensor_key; Type: CONSTRAINT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.node_sensors
    ADD CONSTRAINT node_sensors_node_id_sensor_key UNIQUE (node_id, sensor);


--
-- Name: node_sensors node_sensors_pkey; Type: CONSTRAINT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.node_sensors
    ADD CONSTRAINT node_sensors_pkey PRIMARY KEY (id);


--
-- Name: node_status_history node_status_history_pkey; Type: CONSTRAINT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.node_status_history
    ADD CONSTRAINT node_status_history_pkey PRIMARY KEY (id);


--
-- Name: nodes nodes_pkey; Type: CONSTRAINT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.nodes
    ADD CONSTRAINT nodes_pkey PRIMARY KEY (node_id);


--
-- Name: sensor_readings sensor_readings_pkey; Type: CONSTRAINT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.sensor_readings
    ADD CONSTRAINT sensor_readings_pkey PRIMARY KEY (id);


--
-- Name: sessions sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.sessions
    ADD CONSTRAINT sessions_pkey PRIMARY KEY (id);


--
-- Name: system_config system_config_pkey; Type: CONSTRAINT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.system_config
    ADD CONSTRAINT system_config_pkey PRIMARY KEY (key);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: users users_username_key; Type: CONSTRAINT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_username_key UNIQUE (username);


--
-- Name: videos videos_file_path_key; Type: CONSTRAINT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.videos
    ADD CONSTRAINT videos_file_path_key UNIQUE (file_path);


--
-- Name: videos videos_pkey; Type: CONSTRAINT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.videos
    ADD CONSTRAINT videos_pkey PRIMARY KEY (id);


--
-- Name: idx_alerthist_alert; Type: INDEX; Schema: public; Owner: iot
--

CREATE INDEX idx_alerthist_alert ON public.alert_history USING btree (alert_id, ts DESC);


--
-- Name: idx_alerts_node_ts; Type: INDEX; Schema: public; Owner: iot
--

CREATE INDEX idx_alerts_node_ts ON public.alerts USING btree (node_id, ts DESC);


--
-- Name: idx_alerts_status; Type: INDEX; Schema: public; Owner: iot
--

CREATE INDEX idx_alerts_status ON public.alerts USING btree (status);


--
-- Name: idx_alerts_ts; Type: INDEX; Schema: public; Owner: iot
--

CREATE INDEX idx_alerts_ts ON public.alerts USING btree (ts DESC);


--
-- Name: idx_anom_node_ts; Type: INDEX; Schema: public; Owner: iot
--

CREATE INDEX idx_anom_node_ts ON public.anomalies USING btree (node_id, ts DESC);


--
-- Name: idx_det_node_ts; Type: INDEX; Schema: public; Owner: iot
--

CREATE INDEX idx_det_node_ts ON public.detections USING btree (node_id, ts DESC);


--
-- Name: idx_events_ts; Type: INDEX; Schema: public; Owner: iot
--

CREATE INDEX idx_events_ts ON public.events USING btree (ts DESC);


--
-- Name: idx_hb_node_ts; Type: INDEX; Schema: public; Owner: iot
--

CREATE INDEX idx_hb_node_ts ON public.heartbeats USING btree (node_id, ts DESC);


--
-- Name: idx_nsh_node_ts; Type: INDEX; Schema: public; Owner: iot
--

CREATE INDEX idx_nsh_node_ts ON public.node_status_history USING btree (node_id, ts DESC);


--
-- Name: idx_readings_node_ts; Type: INDEX; Schema: public; Owner: iot
--

CREATE INDEX idx_readings_node_ts ON public.sensor_readings USING btree (node_id, ts DESC);


--
-- Name: idx_sessions_exp; Type: INDEX; Schema: public; Owner: iot
--

CREATE INDEX idx_sessions_exp ON public.sessions USING btree (expires_at);


--
-- Name: idx_sessions_user; Type: INDEX; Schema: public; Owner: iot
--

CREATE INDEX idx_sessions_user ON public.sessions USING btree (user_id);


--
-- Name: idx_vid_node; Type: INDEX; Schema: public; Owner: iot
--

CREATE INDEX idx_vid_node ON public.videos USING btree (node_id, received_at DESC);


--
-- Name: alert_history alert_history_alert_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.alert_history
    ADD CONSTRAINT alert_history_alert_id_fkey FOREIGN KEY (alert_id) REFERENCES public.alerts(id) ON DELETE CASCADE;


--
-- Name: alert_history alert_history_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.alert_history
    ADD CONSTRAINT alert_history_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: alerts alerts_node_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT alerts_node_id_fkey FOREIGN KEY (node_id) REFERENCES public.nodes(node_id);


--
-- Name: alerts alerts_responded_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT alerts_responded_by_fkey FOREIGN KEY (responded_by) REFERENCES public.users(id);


--
-- Name: anomalies anomalies_node_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.anomalies
    ADD CONSTRAINT anomalies_node_id_fkey FOREIGN KEY (node_id) REFERENCES public.nodes(node_id) ON DELETE CASCADE;


--
-- Name: detections detections_node_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.detections
    ADD CONSTRAINT detections_node_id_fkey FOREIGN KEY (node_id) REFERENCES public.nodes(node_id) ON DELETE CASCADE;


--
-- Name: detector_params detector_params_updated_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.detector_params
    ADD CONSTRAINT detector_params_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: events events_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.events
    ADD CONSTRAINT events_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: heartbeats heartbeats_node_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.heartbeats
    ADD CONSTRAINT heartbeats_node_id_fkey FOREIGN KEY (node_id) REFERENCES public.nodes(node_id) ON DELETE CASCADE;


--
-- Name: node_sensors node_sensors_node_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.node_sensors
    ADD CONSTRAINT node_sensors_node_id_fkey FOREIGN KEY (node_id) REFERENCES public.nodes(node_id) ON DELETE CASCADE;


--
-- Name: node_status_history node_status_history_node_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.node_status_history
    ADD CONSTRAINT node_status_history_node_id_fkey FOREIGN KEY (node_id) REFERENCES public.nodes(node_id) ON DELETE CASCADE;


--
-- Name: sensor_readings sensor_readings_node_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.sensor_readings
    ADD CONSTRAINT sensor_readings_node_id_fkey FOREIGN KEY (node_id) REFERENCES public.nodes(node_id) ON DELETE CASCADE;


--
-- Name: sessions sessions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.sessions
    ADD CONSTRAINT sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: videos videos_node_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: iot
--

ALTER TABLE ONLY public.videos
    ADD CONSTRAINT videos_node_id_fkey FOREIGN KEY (node_id) REFERENCES public.nodes(node_id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict 8CPFQvdUssSBnncvxUGvB9dNJ1lft0Gx70XWA79YTwZ1eQ7A8V8qSC72rLCkSGh

