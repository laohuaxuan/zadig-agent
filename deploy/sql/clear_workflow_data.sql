-- 清空审批流运行时数据（保留审批模板、用户与 Agent/Zadig 配置）
USE `zadig_agent`;

SET FOREIGN_KEY_CHECKS = 0;

DELETE FROM `workflow_records`;
DELETE FROM `workflow_tasks`;
DELETE FROM `workflow_ccs`;
DELETE FROM `workflow_instances`;

UPDATE `project_applications`
SET
  `approval_status` = '待审批',
  `process_message` = NULL,
  `execution_log` = NULL,
  `project_url` = '',
  `execution_context_json` = NULL,
  `workflow_instance_id` = NULL;

SET FOREIGN_KEY_CHECKS = 1;
