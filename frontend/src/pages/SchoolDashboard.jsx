import { Link } from "react-router-dom";

function SchoolDashboard() {
  return (
    <div className="school-dashboard">
      <header className="school-header">
        <div className="school-identity">
          <div className="school-logo">
            MTM
          </div>

          <div>
            <h1>MTM Primary School</h1>
            <p>School Management System</p>
          </div>
        </div>

      </header>

      <main className="dashboard-content">
        <section className="dashboard-search">
          <input
            type="search"
            placeholder="Search students, parents, records..."
            aria-label="Search students, parents and records"
          />
        </section>

        <section className="dashboard-navigation">
          <Link to="/school/students" className="dashboard-card">
            <h2>Students</h2>
            <p>Manage student records and information.</p>
          </Link>

          <Link to="/school/parents" className="dashboard-card">
            <h2>Parents</h2>
            <p>Manage parent information and linked students.</p>
          </Link>

          <Link to="/school/academics" className="dashboard-card">
            <h2>Academics</h2>
            <p>Classes, subjects, enrolments and results.</p>
          </Link>

          <Link to="/school/finance" className="dashboard-card">
            <h2>Finance</h2>
            <p>Fees, payments, receipts and ledgers.</p>
          </Link>

          <Link to="/school/communication" className="dashboard-card">
            <h2>Communication</h2>
            <p>Notifications and school communication.</p>
          </Link>

          <Link to="/school/settings" className="dashboard-card">
            <h2>Settings</h2>
            <p>Configure your school's information and preferences.</p>
          </Link>
        </section>
      </main>
    </div>
  );
}

export default SchoolDashboard;