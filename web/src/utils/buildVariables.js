/** 创建项目 / 添加服务时预置的环境变量，用于代理场景下关闭 BuildKit。 */
export function defaultBuildVariables() {
  return [
    {
      key: "DOCKER_BUILDKIT",
      type: "string",
      value: "0",
      options: "",
      multi_value: [],
      scope: "env",
      description: "",
    },
  ];
}
