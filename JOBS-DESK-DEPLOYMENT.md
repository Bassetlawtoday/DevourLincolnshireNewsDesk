# Reusable Jobs Desk

The Jobs Desk has two parts:

1. `jobs_web_server.py` is the HTTPS web service for employer submissions,
   authenticated editorial access and tracked Apply Now redirects.
2. `modules/jobs_desk.py` is the NewsDesk Pro editorial screen. It validates,
   approves or rejects adverts, creates Facebook drafts in the separately
   configured Jobs Metricool brand, shows aggregate Apply Now clicks and builds
   weekly lists grouped by area.

## Privacy boundary

The service does not accept CVs, applications or applicant contact details.
Applications are redirected to the employer. Tracking stores only one daily
integer click total per vacancy: no IP address, cookie, user agent or applicant
identity is stored.

## Hosting settings

Run the service behind HTTPS and set:

- `JOBS_ADMIN_TOKEN`: a long randomly generated editorial API secret.
- `JOBS_HOST`: normally `127.0.0.1` behind a reverse proxy, or the host required
  by the deployment platform.
- `PORT`: the platform port, default `8080`.

Update `config/jobs.json` so `public_base_url` is the final public HTTPS origin.
The same configuration file can contain a later Leicestershire publication;
the processing, validation and database code is not county-specific.

In NewsDesk Pro, open **Jobs Desk → Settings** and enter the hosted service URL,
the same editorial API token, the editor name and the separate Jobs Metricool
brand credentials. The ordinary news Metricool configuration is not reused.

## Public form

For the Lincolnshire publication the form URL is:

`/jobs/advertise/devour_jobs_lincolnshire`

Facebook's action button can link to that URL once the service is deployed.
