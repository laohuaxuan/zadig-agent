-- zadig-agent 平台库结构（参考 mse-domain-binding/deploy/sql）
CREATE DATABASE IF NOT EXISTS `zadig_agent` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `zadig_agent`;

CREATE TABLE IF NOT EXISTS `agents` (
  `id` VARCHAR(64) NOT NULL,
  `name` VARCHAR(128) NOT NULL,
  `api_key` TEXT NOT NULL,
  `model` VARCHAR(256) NOT NULL,
  `models_json` JSON NULL,
  `base_url` VARCHAR(512) NOT NULL,
  `is_default` TINYINT(1) NOT NULL DEFAULT 0,
  `created_at` DATETIME NOT NULL,
  `updated_at` DATETIME NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `settings` (
  `name` VARCHAR(64) NOT NULL,
  `value_json` JSON NOT NULL,
  `updated_at` DATETIME NOT NULL,
  PRIMARY KEY (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `skills` (
  `name` VARCHAR(64) NOT NULL,
  `kind` VARCHAR(16) NOT NULL,
  `display_name` VARCHAR(128) NOT NULL,
  `description` TEXT,
  `content` TEXT,
  `transport` VARCHAR(16) DEFAULT '',
  `command` VARCHAR(512) DEFAULT '',
  `args_json` JSON,
  `url` VARCHAR(512) DEFAULT '',
  `maintainer_id` BIGINT NULL,
  `created_at` DATETIME NOT NULL,
  `updated_at` DATETIME NOT NULL,
  PRIMARY KEY (`name`, `kind`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `agent_templates` (
  `name` VARCHAR(64) NOT NULL,
  `display_name` VARCHAR(128) NOT NULL,
  `description` TEXT,
  `category` VARCHAR(32) NOT NULL DEFAULT 'workflow',
  `body_json` JSON NOT NULL,
  `maintainer_id` BIGINT NULL,
  `created_at` DATETIME NOT NULL,
  `updated_at` DATETIME NOT NULL,
  PRIMARY KEY (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `zadig_instances` (
  `id` VARCHAR(64) NOT NULL,
  `name` VARCHAR(128) NOT NULL,
  `remark` TEXT,
  `base_url` VARCHAR(512) NOT NULL,
  `api_token` TEXT NOT NULL,
  `is_active` TINYINT(1) NOT NULL DEFAULT 0,
  `created_at` DATETIME NOT NULL,
  `updated_at` DATETIME NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `integration_resource_remarks` (
  `resource_type` VARCHAR(32) NOT NULL,
  `resource_key` VARCHAR(128) NOT NULL,
  `remark` TEXT,
  `updated_at` DATETIME NOT NULL,
  PRIMARY KEY (`resource_type`, `resource_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `integration_sync_cache` (
  `resource_type` VARCHAR(32) NOT NULL,
  `items_json` LONGTEXT NOT NULL,
  `synced_at` DATETIME NULL,
  `sync_error` TEXT NULL,
  PRIMARY KEY (`resource_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `project_application_field_defs` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(128) NOT NULL,
  `required` TINYINT(1) NOT NULL DEFAULT 0,
  `field_type` VARCHAR(16) NOT NULL,
  `options_json` JSON NULL,
  `description` VARCHAR(512) NOT NULL DEFAULT '',
  `sort_order` INT NOT NULL DEFAULT 0,
  `enabled` TINYINT(1) NOT NULL DEFAULT 1,
  `options_feishu_source` TINYINT(1) NOT NULL DEFAULT 0,
  `created_at` DATETIME NOT NULL,
  `updated_at` DATETIME NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_field_sort` (`sort_order`),
  KEY `idx_field_enabled` (`enabled`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `project_applications` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `record_id` VARCHAR(64) NOT NULL,
  `initiator_id` BIGINT NOT NULL,
  `project_key` VARCHAR(128) NOT NULL,
  `project_name` VARCHAR(256) NOT NULL,
  `payload_json` JSON NOT NULL,
  `custom_fields_json` JSON NULL,
  `approval_status` VARCHAR(32) NOT NULL DEFAULT '待审批',
  `process_message` TEXT,
  `execution_log` MEDIUMTEXT NULL,
  `project_url` VARCHAR(512) NOT NULL DEFAULT '',
  `execution_context_json` JSON NULL,
  `workflow_instance_id` BIGINT NULL,
  `created_at` DATETIME NOT NULL,
  `updated_at` DATETIME NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_project_app_record` (`record_id`),
  KEY `idx_project_app_initiator` (`initiator_id`),
  KEY `idx_project_app_status` (`approval_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `approval_flow_templates` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(128) NOT NULL,
  `workflow_type` VARCHAR(128) NOT NULL,
  `enabled` TINYINT(1) NOT NULL DEFAULT 1,
  `is_default` TINYINT(1) NOT NULL DEFAULT 0,
  `created_at` DATETIME NOT NULL,
  `updated_at` DATETIME NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_tpl_workflow_type` (`workflow_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `approval_flow_levels` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `template_id` BIGINT NOT NULL,
  `level` INT NOT NULL,
  `name` VARCHAR(64) NOT NULL,
  `approval_mode` VARCHAR(16) NOT NULL DEFAULT 'any',
  PRIMARY KEY (`id`),
  KEY `idx_level_template` (`template_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `approval_flow_level_assignees` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `level_id` BIGINT NOT NULL,
  `user_id` BIGINT NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_assignee_level` (`level_id`),
  KEY `idx_assignee_user` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `approval_flow_level_ccs` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `level_id` BIGINT NOT NULL,
  `user_id` BIGINT NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_cc_level` (`level_id`),
  KEY `idx_cc_user` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workflow_instances` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `serial_no` VARCHAR(32) NOT NULL,
  `title` VARCHAR(256) NOT NULL,
  `workflow_type` VARCHAR(128) NOT NULL,
  `status` VARCHAR(20) NOT NULL,
  `initiator_id` BIGINT NOT NULL,
  `initiator_name` VARCHAR(120) NOT NULL DEFAULT '',
  `summary` VARCHAR(512) NOT NULL DEFAULT '',
  `form_data` JSON NULL,
  `current_node` VARCHAR(64) NOT NULL DEFAULT '',
  `ref_record_id` VARCHAR(64) NOT NULL DEFAULT '',
  `template_id` BIGINT NULL,
  `template_snapshot` JSON NULL,
  `current_level` INT NOT NULL DEFAULT 1,
  `created_at` DATETIME NOT NULL,
  `updated_at` DATETIME NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_workflow_serial` (`serial_no`),
  KEY `idx_workflow_ref` (`ref_record_id`),
  KEY `idx_workflow_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workflow_tasks` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `instance_id` BIGINT NOT NULL,
  `assignee_id` BIGINT NOT NULL,
  `assignee_name` VARCHAR(120) NOT NULL DEFAULT '',
  `status` VARCHAR(20) NOT NULL,
  `node_name` VARCHAR(64) NOT NULL DEFAULT '',
  `level` INT NOT NULL DEFAULT 1,
  `comment` TEXT,
  `processed_at` DATETIME NULL,
  `created_at` DATETIME NOT NULL,
  `updated_at` DATETIME NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_task_instance` (`instance_id`),
  KEY `idx_task_assignee` (`assignee_id`),
  KEY `idx_task_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workflow_records` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `instance_id` BIGINT NOT NULL,
  `node_name` VARCHAR(64) NOT NULL DEFAULT '',
  `user_id` BIGINT NULL,
  `user_name` VARCHAR(120) NOT NULL DEFAULT '',
  `action` VARCHAR(32) NOT NULL,
  `action_label` VARCHAR(64) NOT NULL DEFAULT '',
  `comment` TEXT,
  `created_at` DATETIME NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_record_instance` (`instance_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workflow_ccs` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `instance_id` BIGINT NOT NULL,
  `user_id` BIGINT NOT NULL,
  `read_at` DATETIME NULL,
  `created_at` DATETIME NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_cc_instance` (`instance_id`),
  KEY `idx_cc_user` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `workflow_feishu_cards` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `instance_id` BIGINT NOT NULL,
  `task_id` BIGINT NOT NULL DEFAULT 0,
  `user_id` BIGINT NOT NULL,
  `open_message_id` VARCHAR(128) NOT NULL,
  `open_id` VARCHAR(128) NOT NULL DEFAULT '',
  `created_at` DATETIME NOT NULL,
  `updated_at` DATETIME NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_wfc_instance` (`instance_id`),
  KEY `idx_wfc_user` (`user_id`),
  KEY `idx_wfc_message` (`open_message_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
