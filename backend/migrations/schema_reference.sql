-- schema_reference.sql — DDL PostgreSQL gerado de app/core/models.py
-- Referência (a criação real do banco é via Alembic).

CREATE TABLE audio_protocol (
	id UUID NOT NULL, 
	protocol_id VARCHAR(40) NOT NULL, 
	version VARCHAR(20) NOT NULL, 
	band VARCHAR(8) NOT NULL, 
	carrier_hz NUMERIC(7, 2) NOT NULL, 
	beat_hz NUMERIC(6, 3) NOT NULL, 
	duration_s NUMERIC(7, 1) NOT NULL, 
	target_peak_dbfs NUMERIC(5, 2) NOT NULL, 
	content_hash VARCHAR(64) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_protocol_version UNIQUE (protocol_id, version), 
	CONSTRAINT ck_protocol_band CHECK (band in ('alpha','theta','delta')), 
	CONSTRAINT ck_protocol_positive CHECK (carrier_hz > 0 and duration_s > 0)
);

CREATE TABLE audit_log (
	id UUID NOT NULL, 
	actor_id UUID, 
	actor_type VARCHAR(16) NOT NULL, 
	action VARCHAR(40) NOT NULL, 
	resource_type VARCHAR(40) NOT NULL, 
	resource_id UUID, 
	meta JSONB, 
	occurred_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE participant (
	id UUID NOT NULL, 
	study_code VARCHAR(20) NOT NULL, 
	status VARCHAR(12) DEFAULT 'active' NOT NULL, 
	enrolled_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_participant_status CHECK (status in ('active','withdrawn','completed')), 
	UNIQUE (study_code)
);

CREATE TABLE staff_user (
	id UUID NOT NULL, 
	email VARCHAR(120) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	role VARCHAR(12) NOT NULL, 
	mfa_secret BYTEA, 
	mfa_enabled BOOLEAN DEFAULT false NOT NULL, 
	last_login_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_staff_role CHECK (role in ('researcher','admin')), 
	UNIQUE (email)
);

CREATE TABLE allocation (
	id UUID NOT NULL, 
	participant_id UUID NOT NULL, 
	arm_coded VARCHAR(1) NOT NULL, 
	block INTEGER NOT NULL, 
	sequence_seed_ref VARCHAR(64) NOT NULL, 
	allocated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	unblinded_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_allocation_participant UNIQUE (participant_id), 
	CONSTRAINT ck_allocation_arm CHECK (arm_coded in ('A','B')), 
	FOREIGN KEY(participant_id) REFERENCES participant (id) ON DELETE CASCADE
);

CREATE INDEX ix_allocation_participant_id ON allocation (participant_id);

CREATE TABLE baseline_assessment (
	id UUID NOT NULL, 
	participant_id UUID NOT NULL, 
	gad7_items JSONB NOT NULL, 
	gad7_total SMALLINT NOT NULL, 
	psqi_input JSONB NOT NULL, 
	psqi_global SMALLINT NOT NULL, 
	score_version VARCHAR(20) NOT NULL, 
	assessed_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_baseline_gad7 CHECK (gad7_total between 0 and 21), 
	CONSTRAINT ck_baseline_psqi CHECK (psqi_global between 0 and 21), 
	FOREIGN KEY(participant_id) REFERENCES participant (id) ON DELETE CASCADE
);

CREATE INDEX ix_baseline_assessment_participant_id ON baseline_assessment (participant_id);

CREATE TABLE consent_record (
	id UUID NOT NULL, 
	participant_id UUID NOT NULL, 
	tcle_version VARCHAR(20) NOT NULL, 
	accepted BOOLEAN NOT NULL, 
	accepted_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	ip_address INET, 
	content_hash VARCHAR(64) NOT NULL, 
	revoked_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(participant_id) REFERENCES participant (id) ON DELETE CASCADE
);

CREATE INDEX ix_consent_record_participant_id ON consent_record (participant_id);

CREATE TABLE contact_info (
	id UUID NOT NULL, 
	participant_id UUID NOT NULL, 
	enc_name BYTEA NOT NULL, 
	enc_email BYTEA NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_contact_participant UNIQUE (participant_id), 
	FOREIGN KEY(participant_id) REFERENCES participant (id) ON DELETE CASCADE
);

CREATE INDEX ix_contact_info_participant_id ON contact_info (participant_id);

CREATE TABLE followup_assessment (
	id UUID NOT NULL, 
	participant_id UUID NOT NULL, 
	gad7_total SMALLINT NOT NULL, 
	psqi_global SMALLINT NOT NULL, 
	sus_score SMALLINT NOT NULL, 
	blinding_guess VARCHAR(8), 
	score_version VARCHAR(20) NOT NULL, 
	assessed_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_follow_gad7 CHECK (gad7_total between 0 and 21), 
	CONSTRAINT ck_follow_psqi CHECK (psqi_global between 0 and 21), 
	CONSTRAINT ck_follow_sus CHECK (sus_score between 0 and 100), 
	CONSTRAINT ck_follow_guess CHECK (blinding_guess in ('A','B','nao_sei') or blinding_guess is null), 
	FOREIGN KEY(participant_id) REFERENCES participant (id) ON DELETE CASCADE
);

CREATE INDEX ix_followup_assessment_participant_id ON followup_assessment (participant_id);

CREATE TABLE otp_challenge (
	id UUID NOT NULL, 
	participant_id UUID NOT NULL, 
	code_hash VARCHAR(64) NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	consumed BOOLEAN DEFAULT false NOT NULL, 
	attempts INTEGER DEFAULT 0 NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(participant_id) REFERENCES participant (id) ON DELETE CASCADE
);

CREATE INDEX ix_otp_challenge_participant_id ON otp_challenge (participant_id);

CREATE TABLE screening (
	id UUID NOT NULL, 
	participant_id UUID NOT NULL, 
	eligible BOOLEAN NOT NULL, 
	criteria JSONB NOT NULL, 
	symptoms JSONB, 
	screened_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(participant_id) REFERENCES participant (id) ON DELETE CASCADE
);

CREATE INDEX ix_screening_participant_id ON screening (participant_id);

CREATE TABLE session (
	id UUID NOT NULL, 
	participant_id UUID NOT NULL, 
	protocol_uuid UUID NOT NULL, 
	protocol_hash VARCHAR(64) NOT NULL, 
	started_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	ended_at TIMESTAMP WITH TIME ZONE, 
	effective_seconds INTEGER, 
	interruptions INTEGER DEFAULT 0 NOT NULL, 
	completed BOOLEAN DEFAULT false NOT NULL, 
	headphones_ok BOOLEAN NOT NULL, 
	device_info JSONB, 
	PRIMARY KEY (id), 
	FOREIGN KEY(participant_id) REFERENCES participant (id) ON DELETE CASCADE, 
	FOREIGN KEY(protocol_uuid) REFERENCES audio_protocol (id) ON DELETE RESTRICT
);

CREATE INDEX ix_session_protocol_uuid ON session (protocol_uuid);

CREATE INDEX ix_session_participant_id ON session (participant_id);

CREATE TABLE sleep_diary (
	id UUID NOT NULL, 
	participant_id UUID NOT NULL, 
	diary_date DATE NOT NULL, 
	latency_min INTEGER, 
	awakenings INTEGER, 
	duration_h NUMERIC(4, 2), 
	quality SMALLINT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_diary_day UNIQUE (participant_id, diary_date), 
	FOREIGN KEY(participant_id) REFERENCES participant (id) ON DELETE CASCADE
);

CREATE INDEX ix_sleep_diary_participant_id ON sleep_diary (participant_id);

CREATE TABLE adverse_event (
	id UUID NOT NULL, 
	participant_id UUID NOT NULL, 
	session_id UUID, 
	type VARCHAR(40) NOT NULL, 
	severity VARCHAR(10) NOT NULL, 
	action VARCHAR(200), 
	outcome VARCHAR(200), 
	occurred_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_ae_severity CHECK (severity in ('mild','moderate','severe')), 
	FOREIGN KEY(participant_id) REFERENCES participant (id) ON DELETE CASCADE, 
	FOREIGN KEY(session_id) REFERENCES session (id) ON DELETE SET NULL
);

CREATE INDEX ix_adverse_event_session_id ON adverse_event (session_id);

CREATE INDEX ix_adverse_event_participant_id ON adverse_event (participant_id);

CREATE TABLE post_session_survey (
	id UUID NOT NULL, 
	session_id UUID NOT NULL, 
	feeling SMALLINT NOT NULL, 
	relaxation SMALLINT NOT NULL, 
	slept_better SMALLINT, 
	liked SMALLINT NOT NULL, 
	intensity SMALLINT NOT NULL, 
	would_repeat BOOLEAN NOT NULL, 
	answered_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_survey_session UNIQUE (session_id), 
	CONSTRAINT ck_survey_scales CHECK (feeling between 0 and 4 and relaxation between 0 and 4 and liked between 0 and 4 and intensity between 0 and 4), 
	FOREIGN KEY(session_id) REFERENCES session (id) ON DELETE CASCADE
);

CREATE INDEX ix_post_session_survey_session_id ON post_session_survey (session_id);

CREATE TABLE recommendation_log (
	id UUID NOT NULL, 
	participant_id UUID NOT NULL, 
	session_id UUID, 
	inputs JSONB NOT NULL, 
	rule_id VARCHAR(40) NOT NULL, 
	rule_version VARCHAR(20) NOT NULL, 
	suggested_protocol VARCHAR(40) NOT NULL, 
	accepted BOOLEAN, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(participant_id) REFERENCES participant (id) ON DELETE CASCADE, 
	FOREIGN KEY(session_id) REFERENCES session (id) ON DELETE SET NULL
);

CREATE INDEX ix_recommendation_log_participant_id ON recommendation_log (participant_id);
