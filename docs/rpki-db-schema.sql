drop table if exists bsc;
drop table if exists bsc_cert;
drop table if exists bsc_key;
drop table if exists ca;
drop table if exists ca_detail;
drop table if exists ca_use;
drop table if exists child_ca_link;
drop table if exists child;
drop table if exists child_ca_detail_link;
drop table if exists child_ca_certificate;
drop table if exists ee_cert;
drop table if exists manifest;
drop table if exists manifest_content;
drop table if exists parent;
drop table if exists repos;
drop table if exists roa;
drop table if exists route_origin;
drop table if exists self;
drop table if exists self_pref;
drop table if exists route_origin_prefix;


CREATE TABLE bsc (
       bsc_id               SERIAL NOT NULL,
       priv_key_id          LONGBLOB,
       self_id              BIGINT unsigned NOT NULL,
       pub_key              LONGBLOB,
       PRIMARY KEY (bsc_id)
);


CREATE TABLE bsc_cert (
       bsc_cert_id          SERIAL NOT NULL,
       cert                 LONGBLOB,
       bsc_id               BIGINT unsigned NOT NULL,
       PRIMARY KEY (bsc_cert_id)
);


CREATE TABLE ca (
       ca_id                SERIAL NOT NULL,
       last_crl_sn          BIGINT unsigned,
       last_manifest_sn     BIGINT unsigned,
       next_manifest_update DATETIME,
       next_crl_update      DATETIME,
       last_issued_sn       BIGINT unsigned,
       sia_uri              TEXT,
       parent_id            BIGINT unsigned,
       PRIMARY KEY (ca_id)
);


CREATE TABLE ca_detail (
       ca_detail_id         SERIAL NOT NULL,
       pub_key              LONGBLOB,
       priv_key_handle      LONGBLOB,
       latest_crl           LONGBLOB,
       latest_ca_cert_over_pubkey LONGBLOB,
       manifest_ee_priv_key_handle LONGBLOB,
       manifest_ee_pub_key  LONGBLOB,
       latest_manifest_ee_cert LONGBLOB,
       latest_manifest      LONGBLOB,
       ca_id                BIGINT unsigned NOT NULL,
       PRIMARY KEY (ca_detail_id)
);


CREATE TABLE child (
       child_id             SERIAL NOT NULL,
       ta                   LONGBLOB,
       self_id              BIGINT unsigned NOT NULL,
       bsc_id               BIGINT unsigned NOT NULL,
       PRIMARY KEY (child_id)
);


CREATE TABLE child_ca_certificate (
       child_id             BIGINT unsigned NOT NULL,
       ca_detail_id         BIGINT unsigned NOT NULL,
       cert                 LONGBLOB NOT NULL,
       PRIMARY KEY (child_id, ca_detail_id)
);


CREATE TABLE child_ca_link (
       ca_id                BIGINT unsigned NOT NULL,
       child_id             BIGINT unsigned NOT NULL,
       PRIMARY KEY (ca_id, child_id)
);


CREATE TABLE parent (
       parent_id            SERIAL NOT NULL,
       ta                   LONGBLOB,
       url                  TEXT,
       sia_base             TEXT,
       self_id              BIGINT unsigned NOT NULL,
       bsc_id               BIGINT unsigned NOT NULL,
       repos_id             BIGINT unsigned NOT NULL,
       PRIMARY KEY (parent_id)
);


CREATE TABLE repos (
       repos_id             SERIAL NOT NULL,
       uri                  TEXT,
       ta                   LONGBLOB,
       bsc_id               BIGINT unsigned NOT NULL,
       self_id              BIGINT unsigned NOT NULL,
       PRIMARY KEY (repos_id)
);


CREATE TABLE roa (
       route_origin_id      BIGINT unsigned NOT NULL,
       ee_cert              LONGBLOB,
       roa                  LONGBLOB NOT NULL,
       ca_detail_id         BIGINT unsigned NOT NULL,
       PRIMARY KEY (route_origin_id, ca_detail_id)
);


CREATE TABLE route_origin (
       route_origin_id      SERIAL NOT NULL,
       as_number            DECIMAL(24,0),
       self_id              BIGINT unsigned NOT NULL,
       PRIMARY KEY (route_origin_id)
);


CREATE TABLE route_origin_prefix (
       start_ip             VARCHAR(40),
       end_ip               VARCHAR(40),
       route_origin_id      BIGINT unsigned NOT NULL,
       PRIMARY KEY (route_origin_id, start_ip, end_ip)
);


CREATE TABLE self (
       self_id              SERIAL NOT NULL,
       use_hsm              BOOLEAN,
       PRIMARY KEY (self_id)
);


CREATE TABLE self_pref (
       pref_name            VARCHAR(100),
       pref_value           TEXT,
       self_id              BIGINT unsigned NOT NULL,
       PRIMARY KEY (self_id, pref_name)
);


ALTER TABLE bsc
       ADD FOREIGN KEY (self_id)
                             REFERENCES self;


ALTER TABLE bsc_cert
       ADD FOREIGN KEY (bsc_id)
                             REFERENCES bsc;


ALTER TABLE ca_detail
       ADD FOREIGN KEY (ca_id)
                             REFERENCES ca;


ALTER TABLE child
       ADD FOREIGN KEY (bsc_id)
                             REFERENCES bsc;


ALTER TABLE child
       ADD FOREIGN KEY (self_id)
                             REFERENCES self;


ALTER TABLE child_ca_certificate
       ADD FOREIGN KEY (ca_detail_id)
                             REFERENCES ca_detail;


ALTER TABLE child_ca_certificate
       ADD FOREIGN KEY (child_id)
                             REFERENCES child;


ALTER TABLE child_ca_link
       ADD FOREIGN KEY (child_id)
                             REFERENCES child;


ALTER TABLE child_ca_link
       ADD FOREIGN KEY (ca_id)
                             REFERENCES ca;


ALTER TABLE parent
       ADD FOREIGN KEY (repos_id)
                             REFERENCES repos;


ALTER TABLE parent
       ADD FOREIGN KEY (bsc_id)
                             REFERENCES bsc;


ALTER TABLE parent
       ADD FOREIGN KEY (self_id)
                             REFERENCES self;


ALTER TABLE repos
       ADD FOREIGN KEY (self_id)
                             REFERENCES self;


ALTER TABLE repos
       ADD FOREIGN KEY (bsc_id)
                             REFERENCES bsc;


ALTER TABLE roa
       ADD FOREIGN KEY (ca_detail_id)
                             REFERENCES ca_detail;


ALTER TABLE roa
       ADD FOREIGN KEY (route_origin_id)
                             REFERENCES route_origin;


ALTER TABLE route_origin
       ADD FOREIGN KEY (self_id)
                             REFERENCES self;


ALTER TABLE route_origin_prefix
       ADD FOREIGN KEY (route_origin_id)
                             REFERENCES route_origin;


ALTER TABLE self_pref
       ADD FOREIGN KEY (self_id)
                             REFERENCES self;




