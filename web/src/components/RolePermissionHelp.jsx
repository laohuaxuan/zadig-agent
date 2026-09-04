import { ROLE_OPTIONS } from "../utils/userHelpers.js";

export default function RolePermissionHelp({ selected, options = ROLE_OPTIONS }) {
  return (
    <div className="role-help">
      <div className="role-help-title">权限说明</div>
      {options.map((opt) => (
        <div key={opt.value} className={opt.value === selected ? "role-help-item active" : "role-help-item"}>
          <strong>{opt.label}</strong>
          <span>{opt.desc}</span>
        </div>
      ))}
    </div>
  );
}
