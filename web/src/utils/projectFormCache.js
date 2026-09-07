import {
  fetchApplicant,
  fetchAllProjectEnvironments,
  fetchClusters,
  fetchCodeSources,
  fetchProjectRoles,
  fetchProjects,
  fetchRegistries,
  fetchServiceTemplates,
  fetchUserOptions,
  fetchZadig,
} from "../api.js";

export { fetchAllProjectEnvironments };

export function isProductionEnvironment(item) {
  return item?.production === "true" || item?.production === true;
}

export function environmentTypeLabel(item) {
  return isProductionEnvironment(item) ? "生产环境" : "测试环境";
}

export function formatEnvironmentOption(item) {
  const name = String(item?.env_name || "").trim();
  if (!name) return { value: "", label: "" };
  return {
    value: name,
    label: `${name}（${environmentTypeLabel(item)}）`,
  };
}

export function mapEnvironmentOptions(items) {
  return (items || []).map(formatEnvironmentOption).filter((item) => item.value);
}

const TTL_MS = 2 * 60 * 1000;
const store = new Map();

function readCache(key) {
  const entry = store.get(key);
  if (!entry) return null;
  if (Date.now() - entry.at >= TTL_MS) {
    store.delete(key);
    return null;
  }
  return entry.data;
}

function writeCache(key, data) {
  store.set(key, { data, at: Date.now() });
  return data;
}

async function cached(key, loader) {
  const hit = readCache(key);
  if (hit) return hit;
  const pendingKey = `${key}:pending`;
  if (store.has(pendingKey)) {
    return store.get(pendingKey);
  }
  const pending = loader()
    .then((data) => {
      store.delete(pendingKey);
      return writeCache(key, data);
    })
    .catch((err) => {
      store.delete(pendingKey);
      throw err;
    });
  store.set(pendingKey, pending);
  return pending;
}

function settledItems(result, fallback = []) {
  return result.status === "fulfilled" ? result.value.items || fallback : fallback;
}

function settledItem(result) {
  return result.status === "fulfilled" ? result.value.item || null : null;
}

export function loadCreateProjectOptions() {
  return cached("create-project-options", async () => {
    const results = await Promise.allSettled([
      fetchServiceTemplates({ pageNum: 1, pageSize: 100 }),
      fetchClusters({ pageNum: 1, pageSize: 100 }),
      fetchCodeSources({ pageNum: 1, pageSize: 100 }),
      fetchProjectRoles(),
      fetchUserOptions(),
      fetchZadig(),
      fetchApplicant(),
    ]);
    return {
      templates: settledItems(results[0]),
      clusters: settledItems(results[1]),
      codehosts: settledItems(results[2]),
      roles: settledItems(results[3]),
      users: settledItems(results[4]),
      zadig: settledItem(results[5]),
      applicant: settledItem(results[6]),
    };
  });
}

export function loadServiceAddOptions() {
  return cached("service-add-options", async () => {
    const results = await Promise.allSettled([
      fetchProjects({ pageNum: 1, pageSize: 200 }),
      fetchServiceTemplates({ pageNum: 1, pageSize: 100 }),
      fetchClusters({ pageNum: 1, pageSize: 100 }),
      fetchCodeSources({ pageNum: 1, pageSize: 100 }),
      fetchZadig(),
    ]);
    return {
      projects: settledItems(results[0]),
      templates: settledItems(results[1]),
      clusters: settledItems(results[2]),
      codehosts: settledItems(results[3]),
      zadig: settledItem(results[4]),
      projectsError: results[0].status === "rejected" ? results[0].reason : null,
    };
  });
}

export function loadWorkflowAddOptions() {
  return cached("workflow-add-options", async () => {
    const results = await Promise.allSettled([
      fetchProjects({ pageNum: 1, pageSize: 200 }),
      fetchRegistries({ pageNum: 1, pageSize: 200 }),
      fetchZadig(),
    ]);
    return {
      projects: settledItems(results[0]),
      registries: settledItems(results[1]),
      zadig: settledItem(results[2]),
      projectsError: results[0].status === "rejected" ? results[0].reason : null,
    };
  });
}

export function loadEnvironmentAddOptions() {
  return cached("environment-add-options", async () => {
    const results = await Promise.allSettled([
      fetchProjects({ pageNum: 1, pageSize: 200 }),
      fetchClusters({ pageNum: 1, pageSize: 100 }),
      fetchRegistries({ pageNum: 1, pageSize: 200 }),
      fetchZadig(),
    ]);
    return {
      projects: settledItems(results[0]),
      clusters: settledItems(results[1]),
      registries: settledItems(results[2]),
      zadig: settledItem(results[3]),
      projectsError: results[0].status === "rejected" ? results[0].reason : null,
    };
  });
}
